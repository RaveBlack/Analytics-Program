# AI Blueprint Forge (Unreal Engine 5.0+ Editor Plugin)

This plugin adds an **Editor tab** that sends your prompt to an **OpenAI-compatible HTTP endpoint** and generates **Blueprint Actor assets** (plus component hierarchies like meshes + collisions) from the returned JSON.

## Install (Project Plugin)

1. In your Unreal project folder, create `Plugins/` if it doesn’t exist.
2. Copy this folder into your project:

   - `YourProject/Plugins/AIBlueprintForge/` (this entire folder)

3. Launch the project.
4. Enable the plugin:
   - **Edit → Plugins → AI → AI Blueprint Forge**
5. Restart the editor if prompted (it will compile the plugin).

## Configure the AI endpoint

In Unreal Editor:

- **Edit → Project Settings → Plugins → AI Blueprint Forge**

Set:
- **Endpoint Url**: an OpenAI-compatible `chat/completions` URL
  - Example (OpenAI): `https://api.openai.com/v1/chat/completions`
  - Example (Ollama): `http://localhost:11434/v1/chat/completions`
  - Example (LM Studio): `http://localhost:1234/v1/chat/completions`
- **Model**: model name your endpoint expects (examples: `gpt-4o-mini`, `llama3.1`)
- **API Key**: optional, if your endpoint requires it
- **Default Game Folder**: where generated assets go (default: `/Game/AIForge`)

## Use

Open the tool:
- **Window → AI Blueprint Forge**

Click **Generate Blueprint(s)**.

## Prompt examples

- Beat ’em up enemy:
  - “Create a beat ’em up enemy blueprint: brawler with capsule collision, a simple mesh, and reasonable proportions.”
- Breakable prop:
  - “Generate a breakable crate Actor blueprint with box collision and a static mesh placeholder.”
- Pickup:
  - “Create a pickup Actor blueprint with sphere overlap collision and a visible mesh.”

## AI response format (what your endpoint must return)

Your endpoint should return JSON matching this shape (content-only; no markdown):

```json
{
  "assets": [
    {
      "type": "BlueprintActor",
      "name": "BP_Enemy_Brawler",
      "folder": "/Game/AIForge",
      "parent_class": "/Script/Engine.Actor",
      "components": [
        { "name": "Root", "type": "SceneComponent", "attach_to": null },
        { "name": "Capsule", "type": "CapsuleComponent", "attach_to": "Root", "capsule_radius": 34, "capsule_half_height": 88 },
        { "name": "Mesh", "type": "StaticMeshComponent", "attach_to": "Root", "static_mesh": "/Engine/BasicShapes/Cube.Cube" }
      ],
      "tags": ["AIForge"]
    }
  ]
}
```

## Notes / current limits

- This is an **Editor-only** generator. It creates Blueprints and component trees; it does not yet generate complex Blueprint graphs (combat logic, AI behavior trees, animations).
- Mesh assignment currently supports **StaticMeshComponent** via asset path (with optional Engine basic-shape fallback).

