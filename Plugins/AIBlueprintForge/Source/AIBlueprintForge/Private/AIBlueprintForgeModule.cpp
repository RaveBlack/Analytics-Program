#include "AIBlueprintForgeModule.h"

#include "AIBlueprintForgeApiClient.h"
#include "AIBlueprintForgeBlueprintGenerator.h"
#include "AIBlueprintForgeSettings.h"

#include "Framework/Docking/TabManager.h"
#include "Framework/MultiBox/MultiBoxBuilder.h"
#include "ISettingsModule.h"
#include "LevelEditor.h"
#include "Misc/MessageDialog.h"
#include "ToolMenus.h"
#include "Widgets/Docking/SDockTab.h"
#include "Widgets/Input/SMultiLineEditableTextBox.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SUniformGridPanel.h"
#include "Widgets/Text/STextBlock.h"

const FName FAIBlueprintForgeModule::MainTabName(TEXT("AIBlueprintForge_MainTab"));

namespace
{
	class SAIBlueprintForgePanel : public SCompoundWidget
	{
	public:
		SLATE_BEGIN_ARGS(SAIBlueprintForgePanel) {}
		SLATE_END_ARGS()

		void Construct(const FArguments& InArgs)
		{
			PromptText = FText::FromString(TEXT("Create a beat 'em up enemy blueprint: brawler with capsule collision and a simple mesh."));

			ChildSlot
			[
				SNew(SBorder)
				.Padding(12)
				[
					SNew(SScrollBox)
					+ SScrollBox::Slot()
					[
						SNew(STextBlock)
						.Text(FText::FromString(TEXT("AI Blueprint Forge")))
					]
					+ SScrollBox::Slot()
					.Padding(0, 8)
					[
						SNew(STextBlock)
						.Text(FText::FromString(TEXT("Prompt")))
					]
					+ SScrollBox::Slot()
					[
						SAssignNew(PromptBox, SMultiLineEditableTextBox)
						.Text(PromptText)
						.AutoWrapText(true)
						.OnTextChanged(this, &SAIBlueprintForgePanel::OnPromptChanged)
					]
					+ SScrollBox::Slot()
					.Padding(0, 10)
					[
						SNew(SUniformGridPanel)
						.SlotPadding(FMargin(4))
						+ SUniformGridPanel::Slot(0, 0)
						[
							SAssignNew(GenerateButton, SButton)
							.Text(FText::FromString(TEXT("Generate Blueprint(s)")))
							.OnClicked(this, &SAIBlueprintForgePanel::OnGenerateClicked)
						]
						+ SUniformGridPanel::Slot(1, 0)
						[
							SNew(SButton)
							.Text(FText::FromString(TEXT("Open Settings")))
							.OnClicked(this, &SAIBlueprintForgePanel::OnOpenSettingsClicked)
						]
					]
					+ SScrollBox::Slot()
					.Padding(0, 8)
					[
						SAssignNew(StatusText, STextBlock)
						.Text(FText::FromString(TEXT("Ready.")))
					]
				]
			];
		}

	private:
		void SetBusy(const bool bBusy, const FString& NewStatus)
		{
			if (GenerateButton.IsValid())
			{
				GenerateButton->SetEnabled(!bBusy);
			}
			if (StatusText.IsValid())
			{
				StatusText->SetText(FText::FromString(NewStatus));
			}
		}

		void OnPromptChanged(const FText& NewText)
		{
			PromptText = NewText;
		}

		FReply OnOpenSettingsClicked()
		{
			// Opens Project Settings -> Plugins -> AI Blueprint Forge
			FModuleManager::LoadModuleChecked<ISettingsModule>("Settings").ShowViewer(
				"Project",
				"Plugins",
				"AI Blueprint Forge"
			);
			return FReply::Handled();
		}

		FReply OnGenerateClicked()
		{
			const FString Prompt = PromptText.ToString().TrimStartAndEnd();
			if (Prompt.IsEmpty())
			{
				FMessageDialog::Open(EAppMsgType::Ok, FText::FromString(TEXT("Please enter a prompt first.")));
				return FReply::Handled();
			}

			SetBusy(true, TEXT("Requesting AI plan..."));

			TWeakPtr<SAIBlueprintForgePanel> WeakThis = StaticCastSharedRef<SAIBlueprintForgePanel>(AsShared());
			FAIBlueprintForgeApiClient::RequestBlueprintPlan(Prompt, [WeakThis](const FAIBlueprintForgeAIResult& Result)
			{
				if (!WeakThis.IsValid())
				{
					return;
				}

				if (!Result.bOk)
				{
					WeakThis.Pin()->SetBusy(false, FString::Printf(TEXT("Error: %s"), *Result.Error));
					return;
				}

				WeakThis.Pin()->SetBusy(true, TEXT("Generating assets in Content Browser..."));

				const FAIBlueprintForgeGenerateResult Gen = FAIBlueprintForgeBlueprintGenerator::GenerateFromJson(Result.JsonText);
				if (!Gen.bOk)
				{
					WeakThis.Pin()->SetBusy(false, FString::Printf(TEXT("Generation failed: %s"), *Gen.Error));
					return;
				}

				FString Summary = TEXT("Done. Created:\n");
				for (const FString& Asset : Gen.CreatedAssets)
				{
					Summary += TEXT("- ") + Asset + TEXT("\n");
				}
				WeakThis.Pin()->SetBusy(false, Summary);
			});

			return FReply::Handled();
		}

	private:
		FText PromptText;
		TSharedPtr<SMultiLineEditableTextBox> PromptBox;
		TSharedPtr<SButton> GenerateButton;
		TSharedPtr<STextBlock> StatusText;
	};
}

void FAIBlueprintForgeModule::StartupModule()
{
	RegisterTabSpawner();

	UToolMenus::RegisterStartupCallback(FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FAIBlueprintForgeModule::RegisterMenus));
}

void FAIBlueprintForgeModule::ShutdownModule()
{
	UToolMenus::UnRegisterStartupCallback(this);
	UToolMenus::UnregisterOwner(this);

	UnregisterTabSpawner();
}

void FAIBlueprintForgeModule::RegisterTabSpawner()
{
	FGlobalTabmanager::Get()->RegisterNomadTabSpawner(MainTabName, FOnSpawnTab::CreateRaw(this, &FAIBlueprintForgeModule::SpawnMainTab))
		.SetDisplayName(FText::FromString(TEXT("AI Blueprint Forge")))
		.SetMenuType(ETabSpawnerMenuType::Hidden);
}

void FAIBlueprintForgeModule::UnregisterTabSpawner()
{
	FGlobalTabmanager::Get()->UnregisterNomadTabSpawner(MainTabName);
}

TSharedRef<SDockTab> FAIBlueprintForgeModule::SpawnMainTab(const FSpawnTabArgs& Args)
{
	return SNew(SDockTab)
		.TabRole(ETabRole::NomadTab)
		[
			SNew(SAIBlueprintForgePanel)
		];
}

void FAIBlueprintForgeModule::RegisterMenus()
{
	FToolMenuOwnerScoped OwnerScoped(this);

	UToolMenu* Menu = UToolMenus::Get()->ExtendMenu("LevelEditor.MainMenu.Window");
	FToolMenuSection& Section = Menu->FindOrAddSection("WindowLayout");

	Section.AddMenuEntry(
		"AIBlueprintForge_OpenTab",
		FText::FromString(TEXT("AI Blueprint Forge")),
		FText::FromString(TEXT("Open AI Blueprint Forge tab")),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateLambda([]()
		{
			FGlobalTabmanager::Get()->TryInvokeTab(FAIBlueprintForgeModule::MainTabName);
		}))
	);
}

IMPLEMENT_MODULE(FAIBlueprintForgeModule, AIBlueprintForge)

