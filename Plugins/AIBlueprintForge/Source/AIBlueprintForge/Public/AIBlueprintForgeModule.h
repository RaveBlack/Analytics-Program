#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"

class FAIBlueprintForgeModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

private:
	void RegisterMenus();
	void RegisterTabSpawner();
	void UnregisterTabSpawner();

	TSharedRef<class SDockTab> SpawnMainTab(const class FSpawnTabArgs& Args);

	static const FName MainTabName;
};

