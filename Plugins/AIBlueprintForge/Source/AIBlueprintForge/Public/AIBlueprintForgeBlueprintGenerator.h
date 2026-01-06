#pragma once

#include "CoreMinimal.h"

struct FAIBlueprintForgeGenerateResult
{
	bool bOk = false;
	FString Error;
	TArray<FString> CreatedAssets;
};

class FAIBlueprintForgeBlueprintGenerator
{
public:
	static FAIBlueprintForgeGenerateResult GenerateFromJson(const FString& JsonText);
};

