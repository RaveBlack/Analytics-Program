#include "AIBlueprintForgeBlueprintGenerator.h"

#include "AIBlueprintForgeSettings.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetToolsModule.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SCS_Node.h"
#include "Engine/SimpleConstructionScript.h"
#include "Engine/StaticMesh.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Json.h"
#include "Misc/PackageName.h"
#include "ObjectTools.h"
#include "UObject/Package.h"

namespace
{
	static const UAIBlueprintForgeSettings* GetSettings()
	{
		return GetDefault<UAIBlueprintForgeSettings>();
	}

	static FString GetStringOrEmpty(const TSharedPtr<FJsonObject>& Obj, const FString& Field)
	{
		if (!Obj.IsValid())
		{
			return FString();
		}
		FString Out;
		Obj->TryGetStringField(Field, Out);
		return Out;
	}

	static FString GetAttachToName(const TSharedPtr<FJsonObject>& Obj)
	{
		if (!Obj.IsValid())
		{
			return FString();
		}

		const TSharedPtr<FJsonValue> Field = Obj->TryGetField(TEXT("attach_to"));
		if (!Field.IsValid() || Field->IsNull())
		{
			return FString();
		}
		if (Field->Type == EJson::String)
		{
			return Field->AsString();
		}
		return FString();
	}

	static bool TryGetVec3(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Field, FVector& Out)
	{
		if (!Obj.IsValid())
		{
			return false;
		}

		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (!Obj->TryGetArrayField(Field, Arr) || !Arr || Arr->Num() < 3)
		{
			return false;
		}

		Out.X = static_cast<float>((*Arr)[0]->AsNumber());
		Out.Y = static_cast<float>((*Arr)[1]->AsNumber());
		Out.Z = static_cast<float>((*Arr)[2]->AsNumber());
		return true;
	}

	static bool TryGetRot3(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Field, FRotator& Out)
	{
		FVector V;
		if (!TryGetVec3(Obj, Field, V))
		{
			return false;
		}
		Out = FRotator(V.X, V.Y, V.Z);
		return true;
	}

	static UClass* ResolveComponentClass(const FString& Type)
	{
		if (Type.Equals(TEXT("SceneComponent"), ESearchCase::IgnoreCase))
		{
			return USceneComponent::StaticClass();
		}
		if (Type.Equals(TEXT("StaticMeshComponent"), ESearchCase::IgnoreCase))
		{
			return UStaticMeshComponent::StaticClass();
		}
		if (Type.Equals(TEXT("SkeletalMeshComponent"), ESearchCase::IgnoreCase))
		{
			return USkeletalMeshComponent::StaticClass();
		}
		if (Type.Equals(TEXT("CapsuleComponent"), ESearchCase::IgnoreCase))
		{
			return UCapsuleComponent::StaticClass();
		}
		if (Type.Equals(TEXT("BoxComponent"), ESearchCase::IgnoreCase))
		{
			return UBoxComponent::StaticClass();
		}
		if (Type.Equals(TEXT("SphereComponent"), ESearchCase::IgnoreCase))
		{
			return USphereComponent::StaticClass();
		}
		return nullptr;
	}

	static UClass* ResolveParentClass(const FString& ParentClassPath)
	{
		if (!ParentClassPath.IsEmpty())
		{
			if (UClass* Cls = LoadObject<UClass>(nullptr, *ParentClassPath))
			{
				return Cls;
			}
			if (UClass* Cls2 = StaticLoadClass(UObject::StaticClass(), nullptr, *ParentClassPath))
			{
				return Cls2;
			}
		}
		return AActor::StaticClass();
	}

	static FString MakeValidGameFolder(const FString& FolderCandidate)
	{
		FString Folder = FolderCandidate.TrimStartAndEnd();
		if (Folder.IsEmpty())
		{
			Folder = GetSettings() ? GetSettings()->DefaultGameFolder : TEXT("/Game/AIForge");
		}
		if (!Folder.StartsWith(TEXT("/")))
		{
			Folder = TEXT("/") + Folder;
		}
		if (!Folder.StartsWith(TEXT("/Game")))
		{
			Folder = TEXT("/Game/AIForge");
		}
		return Folder;
	}

	static FString PickFallbackStaticMeshPath()
	{
		return TEXT("/Engine/BasicShapes/Cube.Cube");
	}

	static UStaticMesh* LoadStaticMeshOrFallback(const FString& Path)
	{
		const UAIBlueprintForgeSettings* Settings = GetSettings();
		const FString Candidate = Path.TrimStartAndEnd();

		if (!Candidate.IsEmpty())
		{
			if (UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *Candidate))
			{
				return Mesh;
			}
		}

		if (Settings && Settings->bAllowEngineBasicShapeFallbacks)
		{
			return LoadObject<UStaticMesh>(nullptr, *PickFallbackStaticMeshPath());
		}
		return nullptr;
	}
}

FAIBlueprintForgeGenerateResult FAIBlueprintForgeBlueprintGenerator::GenerateFromJson(const FString& JsonText)
{
	FAIBlueprintForgeGenerateResult Out;

	TSharedPtr<FJsonObject> Root;
	{
		TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonText);
		if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
		{
			Out.bOk = false;
			Out.Error = TEXT("Invalid JSON (expected object).");
			return Out;
		}
	}

	const TArray<TSharedPtr<FJsonValue>>* Assets = nullptr;
	if (!Root->TryGetArrayField(TEXT("assets"), Assets) || !Assets)
	{
		Out.bOk = false;
		Out.Error = TEXT("JSON missing 'assets' array.");
		return Out;
	}

	IAssetTools& AssetTools = FModuleManager::LoadModuleChecked<FAssetToolsModule>("AssetTools").Get();

	for (const TSharedPtr<FJsonValue>& AssetVal : *Assets)
	{
		const TSharedPtr<FJsonObject> AssetObj = AssetVal.IsValid() ? AssetVal->AsObject() : nullptr;
		if (!AssetObj.IsValid())
		{
			continue;
		}

		const FString Type = GetStringOrEmpty(AssetObj, TEXT("type"));
		if (!Type.Equals(TEXT("BlueprintActor"), ESearchCase::IgnoreCase))
		{
			continue;
		}

		const FString NameRaw = GetStringOrEmpty(AssetObj, TEXT("name"));
		if (NameRaw.IsEmpty())
		{
			continue;
		}

		const FString Folder = MakeValidGameFolder(GetStringOrEmpty(AssetObj, TEXT("folder")));
		const FString SafeName = ObjectTools::SanitizeObjectName(NameRaw);

		FString PackageName;
		FString AssetName;
		AssetTools.CreateUniqueAssetName(Folder + TEXT("/") + SafeName, TEXT(""), PackageName, AssetName);

		if (!FPackageName::IsValidLongPackageName(PackageName, /*bIncludeReadOnlyRoots*/false))
		{
			PackageName = TEXT("/Game/AIForge/") + AssetName;
		}

		UPackage* Package = CreatePackage(*PackageName);
		if (!Package)
		{
			continue;
		}

		const FString ParentPath = GetStringOrEmpty(AssetObj, TEXT("parent_class"));
		UClass* ParentClass = ResolveParentClass(ParentPath);

		UBlueprint* Blueprint = FKismetEditorUtilities::CreateBlueprint(
			ParentClass,
			Package,
			*AssetName,
			BPTYPE_Normal,
			UBlueprint::StaticClass(),
			UBlueprintGeneratedClass::StaticClass(),
			FName(TEXT("AIBlueprintForge"))
		);

		if (!Blueprint)
		{
			continue;
		}

		USimpleConstructionScript* SCS = Blueprint->SimpleConstructionScript;
		if (!SCS)
		{
			continue;
		}

		// Use existing default root if present.
		USCS_Node* DefaultRoot = nullptr;
		{
			const TArray<USCS_Node*>& Roots = SCS->GetRootNodes();
			if (Roots.Num() > 0)
			{
				DefaultRoot = Roots[0];
			}
		}

		TMap<FString, USCS_Node*> NameToNode;
		if (DefaultRoot)
		{
			NameToNode.Add(TEXT("Root"), DefaultRoot);
			NameToNode.Add(DefaultRoot->GetVariableName().ToString(), DefaultRoot);
		}

		// Pass 1: create nodes (except conceptual Root that maps to default root).
		const TArray<TSharedPtr<FJsonValue>>* Components = nullptr;
		if (AssetObj->TryGetArrayField(TEXT("components"), Components) && Components)
		{
			for (const TSharedPtr<FJsonValue>& CompVal : *Components)
			{
				const TSharedPtr<FJsonObject> CompObj = CompVal.IsValid() ? CompVal->AsObject() : nullptr;
				if (!CompObj.IsValid())
				{
					continue;
				}

				const FString CompName = GetStringOrEmpty(CompObj, TEXT("name"));
				const FString CompType = GetStringOrEmpty(CompObj, TEXT("type"));
				const FString AttachTo = GetAttachToName(CompObj);

				if (CompName.IsEmpty() || CompType.IsEmpty())
				{
					continue;
				}

				// If the AI declares a "Root" SceneComponent with attach_to null, map it to the default root.
				if (DefaultRoot
					&& CompType.Equals(TEXT("SceneComponent"), ESearchCase::IgnoreCase)
					&& CompName.Equals(TEXT("Root"), ESearchCase::IgnoreCase)
					&& AttachTo.IsEmpty())
				{
					NameToNode.Add(CompName, DefaultRoot);
					continue;
				}

				UClass* ComponentClass = ResolveComponentClass(CompType);
				if (!ComponentClass)
				{
					continue;
				}

				USCS_Node* Node = SCS->CreateNode(ComponentClass, FName(*ObjectTools::SanitizeObjectName(CompName)));
				if (!Node)
				{
					continue;
				}

				// Defer parenting to pass 2.
				SCS->AddNode(Node);
				NameToNode.Add(CompName, Node);
			}

			// Pass 2: attach + configure templates.
			for (const TSharedPtr<FJsonValue>& CompVal : *Components)
			{
				const TSharedPtr<FJsonObject> CompObj = CompVal.IsValid() ? CompVal->AsObject() : nullptr;
				if (!CompObj.IsValid())
				{
					continue;
				}

				const FString CompName = GetStringOrEmpty(CompObj, TEXT("name"));
				if (CompName.IsEmpty())
				{
					continue;
				}

				USCS_Node** NodePtr = NameToNode.Find(CompName);
				if (!NodePtr || !(*NodePtr))
				{
					continue;
				}
				USCS_Node* Node = *NodePtr;

				// Parent it
				USCS_Node* ParentNode = DefaultRoot;
				{
					const FString AttachTo = GetAttachToName(CompObj);
					if (!AttachTo.IsEmpty())
					{
						if (USCS_Node** ParentPtr = NameToNode.Find(AttachTo))
						{
							ParentNode = *ParentPtr;
						}
					}
				}
				if (ParentNode && ParentNode != Node)
				{
					Node->SetParent(ParentNode);
					ParentNode->AddChildNode(Node);
				}

				// Configure transform
				if (USceneComponent* SceneTemplate = Cast<USceneComponent>(Node->ComponentTemplate))
				{
					FVector Loc;
					if (TryGetVec3(CompObj, TEXT("relative_location"), Loc))
					{
						SceneTemplate->SetRelativeLocation(Loc);
					}
					FRotator Rot;
					if (TryGetRot3(CompObj, TEXT("relative_rotation"), Rot))
					{
						SceneTemplate->SetRelativeRotation(Rot);
					}
					FVector Scl;
					if (TryGetVec3(CompObj, TEXT("relative_scale"), Scl))
					{
						SceneTemplate->SetRelativeScale3D(Scl);
					}
				}

				// Type-specific configuration
				if (UStaticMeshComponent* SMC = Cast<UStaticMeshComponent>(Node->ComponentTemplate))
				{
					const FString MeshPath = GetStringOrEmpty(CompObj, TEXT("static_mesh"));
					if (UStaticMesh* Mesh = LoadStaticMeshOrFallback(MeshPath))
					{
						SMC->SetStaticMesh(Mesh);
					}
				}
				else if (UCapsuleComponent* Capsule = Cast<UCapsuleComponent>(Node->ComponentTemplate))
				{
					double Radius = 34.0;
					double HalfHeight = 88.0;
					CompObj->TryGetNumberField(TEXT("capsule_radius"), Radius);
					CompObj->TryGetNumberField(TEXT("capsule_half_height"), HalfHeight);
					Capsule->SetCapsuleSize(static_cast<float>(Radius), static_cast<float>(HalfHeight));
				}
				else if (UBoxComponent* Box = Cast<UBoxComponent>(Node->ComponentTemplate))
				{
					FVector Ext(50, 50, 50);
					TryGetVec3(CompObj, TEXT("box_extent"), Ext);
					Box->SetBoxExtent(Ext);
				}
				else if (USphereComponent* Sphere = Cast<USphereComponent>(Node->ComponentTemplate))
				{
					double Radius = 50.0;
					CompObj->TryGetNumberField(TEXT("sphere_radius"), Radius);
					Sphere->SetSphereRadius(static_cast<float>(Radius));
				}
			}
		}

		FKismetEditorUtilities::CompileBlueprint(Blueprint);
		FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
		FAssetRegistryModule::AssetCreated(Blueprint);
		Package->MarkPackageDirty();

		Out.CreatedAssets.Add(PackageName);
	}

	Out.bOk = Out.CreatedAssets.Num() > 0;
	if (!Out.bOk)
	{
		Out.Error = TEXT("No assets were created. Check the AI response schema (expected assets[].type == BlueprintActor).");
	}
	return Out;
}

