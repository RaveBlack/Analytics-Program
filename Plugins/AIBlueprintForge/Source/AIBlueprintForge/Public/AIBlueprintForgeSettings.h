#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "AIBlueprintForgeSettings.generated.h"

UCLASS(Config=EditorPerProjectUserSettings, DefaultConfig, meta=(DisplayName="AI Blueprint Forge"))
class AIBLUEPRINTFORGE_API UAIBlueprintForgeSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	/** OpenAI-compatible endpoint. Examples: https://api.openai.com/v1/chat/completions, http://localhost:11434/v1/chat/completions */
	UPROPERTY(Config, EditAnywhere, Category="AI")
	FString EndpointUrl = TEXT("https://api.openai.com/v1/chat/completions");

	/** Model name for your endpoint (e.g. gpt-4o-mini, gpt-4.1-mini, llama3.1, etc.). */
	UPROPERTY(Config, EditAnywhere, Category="AI")
	FString Model = TEXT("gpt-4o-mini");

	/** API key (if your endpoint requires one). */
	UPROPERTY(Config, EditAnywhere, Category="AI", meta=(DisplayName="API Key", PasswordField=true))
	FString ApiKey;

	/** Where to place generated Blueprints (e.g. /Game/AIForge). */
	UPROPERTY(Config, EditAnywhere, Category="Generation")
	FString DefaultGameFolder = TEXT("/Game/AIForge");

	/** If true, we will allow creating placeholder meshes (Engine basic shapes) when AI returns empty mesh paths. */
	UPROPERTY(Config, EditAnywhere, Category="Generation")
	bool bAllowEngineBasicShapeFallbacks = true;
};

