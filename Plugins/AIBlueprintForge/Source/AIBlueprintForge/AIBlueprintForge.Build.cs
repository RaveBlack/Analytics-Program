using UnrealBuildTool;

public class AIBlueprintForge : ModuleRules
{
	public AIBlueprintForge(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(
			new string[]
			{
				"Core",
				"CoreUObject",
				"Engine"
			}
		);

		PrivateDependencyModuleNames.AddRange(
			new string[]
			{
				"Projects",
				"Slate",
				"SlateCore",
				"Settings",
				"ToolMenus",
				"UnrealEd",
				"AssetTools",
				"EditorStyle",
				"LevelEditor",
				"Kismet",
				"KismetCompiler",
				"BlueprintGraph",
				"Http",
				"Json",
				"JsonUtilities",
				"DeveloperSettings"
			}
		);
	}
}

