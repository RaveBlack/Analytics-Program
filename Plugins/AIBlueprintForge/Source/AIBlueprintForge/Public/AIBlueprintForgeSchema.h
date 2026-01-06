#pragma once

#include "CoreMinimal.h"

/**
 * JSON schema used for AI responses.
 *
 * Expected top-level:
 * {
 *   "assets": [
 *     {
 *       "type": "BlueprintActor",
 *       "name": "BP_Example",
 *       "folder": "/Game/AIForge",
 *       "parent_class": "/Script/Engine.Actor",
 *       "components": [
 *         { "name":"Root", "type":"SceneComponent", "attach_to": null },
 *         { "name":"Mesh", "type":"StaticMeshComponent", "attach_to":"Root", "static_mesh":"/Engine/BasicShapes/Cube.Cube" }
 *       ],
 *       "tags": ["AIForge"]
 *     }
 *   ]
 * }
 */
namespace AIBlueprintForgeSchema
{
	static const TCHAR* SystemPrompt = TEXT(
		"You are an Unreal Engine 5 editor automation assistant. "
		"Return ONLY valid JSON (no markdown, no code fences). "
		"Your JSON MUST match this shape:\n"
		"{\"assets\":[{\"type\":\"BlueprintActor\",\"name\":\"BP_Name\",\"folder\":\"/Game/Folder\",\"parent_class\":\"/Script/Engine.Actor\",\"components\":[{\"name\":\"Root\",\"type\":\"SceneComponent\",\"attach_to\":null}],\"tags\":[\"AIForge\"]}]}\n"
		"Component rules:\n"
		"- type is one of: SceneComponent, StaticMeshComponent, SkeletalMeshComponent, CapsuleComponent, BoxComponent, SphereComponent.\n"
		"- attach_to references another component's name or null.\n"
		"- For StaticMeshComponent, prefer using engine basic shapes if unsure: /Engine/BasicShapes/Cube.Cube, Sphere.Sphere, Cylinder.Cylinder, Cone.Cone, Plane.Plane.\n"
		"- Provide reasonable defaults; keep it simple.\n"
		"Do NOT invent plugin-specific classes. Use standard Engine component types."
	);
}

