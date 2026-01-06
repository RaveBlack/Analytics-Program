#include "AIBlueprintForgeApiClient.h"

#include "AIBlueprintForgeSchema.h"
#include "AIBlueprintForgeSettings.h"

#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Json.h"
#include "JsonObjectConverter.h"
#include "Misc/ScopeExit.h"

namespace
{
	constexpr float RequestTimeoutSeconds = 120.0f;

	static const UAIBlueprintForgeSettings* GetSettings()
	{
		return GetDefault<UAIBlueprintForgeSettings>();
	}

	static void Complete(TFunction<void(const FAIBlueprintForgeAIResult&)> OnDone, const FAIBlueprintForgeAIResult& Result)
	{
		if (OnDone)
		{
			OnDone(Result);
		}
	}
}

void FAIBlueprintForgeApiClient::RequestBlueprintPlan(
	const FString& UserPrompt,
	TFunction<void(const FAIBlueprintForgeAIResult& Result)> OnDone)
{
	const UAIBlueprintForgeSettings* Settings = GetSettings();
	if (!Settings)
	{
		FAIBlueprintForgeAIResult R;
		R.bOk = false;
		R.Error = TEXT("Settings missing.");
		return Complete(MoveTemp(OnDone), R);
	}

	const FString Url = Settings->EndpointUrl.TrimStartAndEnd();
	if (Url.IsEmpty())
	{
		FAIBlueprintForgeAIResult R;
		R.bOk = false;
		R.Error = TEXT("EndpointUrl is empty. Set it in Project Settings -> Plugins -> AI Blueprint Forge.");
		return Complete(MoveTemp(OnDone), R);
	}

	TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("model"), Settings->Model);

	TArray<TSharedPtr<FJsonValue>> Messages;
	{
		TSharedPtr<FJsonObject> Sys = MakeShared<FJsonObject>();
		Sys->SetStringField(TEXT("role"), TEXT("system"));
		Sys->SetStringField(TEXT("content"), AIBlueprintForgeSchema::SystemPrompt);
		Messages.Add(MakeShared<FJsonValueObject>(Sys));

		TSharedPtr<FJsonObject> User = MakeShared<FJsonObject>();
		User->SetStringField(TEXT("role"), TEXT("user"));
		User->SetStringField(TEXT("content"), UserPrompt);
		Messages.Add(MakeShared<FJsonValueObject>(User));
	}

	Root->SetArrayField(TEXT("messages"), Messages);
	Root->SetNumberField(TEXT("temperature"), 0.2);

	FString Body;
	{
		TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Body);
		FJsonSerializer::Serialize(Root.ToSharedRef(), Writer);
	}

	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req = FHttpModule::Get().CreateRequest();
	Req->SetURL(Url);
	Req->SetVerb(TEXT("POST"));
	Req->SetTimeout(RequestTimeoutSeconds);
	Req->SetHeader(TEXT("Content-Type"), TEXT("application/json"));

	const FString ApiKey = Settings->ApiKey.TrimStartAndEnd();
	if (!ApiKey.IsEmpty())
	{
		Req->SetHeader(TEXT("Authorization"), FString::Printf(TEXT("Bearer %s"), *ApiKey));
	}

	Req->SetContentAsString(Body);
	Req->OnProcessRequestComplete().BindLambda(
		[OnDone = MoveTemp(OnDone)](FHttpRequestPtr Request, FHttpResponsePtr Response, bool bSucceeded)
		{
			FAIBlueprintForgeAIResult R;

			if (!bSucceeded || !Response.IsValid())
			{
				R.bOk = false;
				R.Error = TEXT("Request failed (no response). Check endpoint URL and that your model server is running.");
				return Complete(OnDone, R);
			}

			const int32 Code = Response->GetResponseCode();
			const FString RespText = Response->GetContentAsString();
			R.RawText = RespText;

			if (Code < 200 || Code >= 300)
			{
				R.bOk = false;
				R.Error = FString::Printf(TEXT("HTTP %d. Response: %s"), Code, *RespText.Left(1200));
				return Complete(OnDone, R);
			}

			// Many OpenAI-compatible endpoints respond with:
			// { choices: [ { message: { content: "..." } } ] }
			FString ContentCandidate;
			{
				TSharedPtr<FJsonObject> Obj;
				TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(RespText);
				if (FJsonSerializer::Deserialize(Reader, Obj) && Obj.IsValid())
				{
					const TArray<TSharedPtr<FJsonValue>>* Choices = nullptr;
					if (Obj->TryGetArrayField(TEXT("choices"), Choices) && Choices && Choices->Num() > 0)
					{
						const TSharedPtr<FJsonObject> ChoiceObj = (*Choices)[0].IsValid() ? (*Choices)[0]->AsObject() : nullptr;
						if (ChoiceObj.IsValid())
						{
							TSharedPtr<FJsonObject> MessageObj;
							if (ChoiceObj->TryGetObjectField(TEXT("message"), MessageObj) && MessageObj.IsValid())
							{
								MessageObj->TryGetStringField(TEXT("content"), ContentCandidate);
							}
						}
					}
					else
					{
						// Some local servers just return { "content": "..." } or the JSON itself.
						Obj->TryGetStringField(TEXT("content"), ContentCandidate);
					}
				}
			}

			const FString Candidate = ContentCandidate.IsEmpty() ? RespText : ContentCandidate;
			const FString JsonText = ExtractFirstJsonObject(Candidate);
			if (JsonText.IsEmpty())
			{
				R.bOk = false;
				R.Error = TEXT("AI response did not contain a JSON object. Ensure your endpoint returns JSON-only content.");
				return Complete(OnDone, R);
			}

			// Validate that it parses as JSON object.
			{
				TSharedPtr<FJsonObject> Check;
				TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonText);
				if (!FJsonSerializer::Deserialize(Reader, Check) || !Check.IsValid())
				{
					R.bOk = false;
					R.Error = FString::Printf(TEXT("Extracted JSON was invalid. First 800 chars: %s"), *JsonText.Left(800));
					return Complete(OnDone, R);
				}
			}

			R.bOk = true;
			R.JsonText = JsonText;
			return Complete(OnDone, R);
		});

	Req->ProcessRequest();
}

FString FAIBlueprintForgeApiClient::ExtractFirstJsonObject(const FString& Text)
{
	int32 Start = INDEX_NONE;
	int32 Depth = 0;
	for (int32 i = 0; i < Text.Len(); i++)
	{
		const TCHAR C = Text[i];
		if (C == '{')
		{
			if (Depth == 0)
			{
				Start = i;
			}
			Depth++;
		}
		else if (C == '}')
		{
			if (Depth > 0)
			{
				Depth--;
				if (Depth == 0 && Start != INDEX_NONE)
				{
					return Text.Mid(Start, i - Start + 1);
				}
			}
		}
	}
	return FString();
}

