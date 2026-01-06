#pragma once

#include "CoreMinimal.h"

class FHttpRequestPtr;
class FHttpResponsePtr;

struct FAIBlueprintForgeAIResult
{
	bool bOk = false;
	FString Error;
	FString RawText;
	FString JsonText;
};

class FAIBlueprintForgeApiClient
{
public:
	static void RequestBlueprintPlan(
		const FString& UserPrompt,
		TFunction<void(const FAIBlueprintForgeAIResult& Result)> OnDone);

private:
	static FString ExtractFirstJsonObject(const FString& Text);
};

