# Unreal AI Integration Hub (VS Code Extension)

This is a **TypeScript VS Code extension** that acts as a **control hub** for Unreal Engine AI integration:

- Submit **UPS (Universal Prompt Schema)** prompts to a backend
- View pending prompts in a **tree view**
- Fetch build / patch results into an **Output** panel
- Watch a folder (default: `/UnrealBridge/pending_prompts/`) and auto-submit new JSON files
- Generate Unreal **plugin skeletons** (`.uplugin` + module folders + empty C++ files)
- Create **Blueprint patch templates** (JSON)

## Quick start

```bash
cd /workspace/unreal-ai-integration-hub
npm install
npm run compile
```

Then in VS Code:

- Open the folder `unreal-ai-integration-hub`
- Press **F5** to launch the Extension Development Host
- Use the Command Palette to run:
  - **Unreal AI Hub: Submit UPS Prompt**
  - **Unreal AI Hub: View Pending Prompts**
  - **Unreal AI Hub: Fetch Build Result**
  - **Unreal AI Hub: Generate Plugin Skeleton**
  - **Unreal AI Hub: New Blueprint Patch Template**

## Backend API expectations

Default backend URL: `http://localhost:5000`

- **POST** `/prompt/submit`  
  Body: UPS JSON
- **GET** `/prompt/pending`  
  Response: array of `{ prompt_id, scope, ... }`
- **GET** `/prompt/result?prompt_id=...`  
  Response: build result payload (errors, diffs, logs, etc.)

These are configurable via:

- VS Code Settings: `unrealAiHub.backendUrl`
- Project `config.json` in the extension folder

## Configuration

The extension reads config in this order:

1. VS Code settings (`unrealAiHub.*`)
2. Local `config.json` (this repository)
3. Built-in defaults

Key settings:

- **backendUrl**: Base backend URL
- **pendingPromptsFolder**: Folder to watch for new JSON files
- **upsSchemaPath**: JSON Schema file used for strict UPS validation

## Templates

Templates live under `unreal_templates/`:

- `unreal_templates/uplugin/` - `.uplugin` skeleton templates
- `unreal_templates/blueprint_patch/` - Blueprint patch JSON templates
- `unreal_templates/ups/ups.schema.json` - UPS JSON Schema used for validation

## Notes / constraints

- No AI models run inside VS Code. This is strictly a tool for moving JSON prompts/results and generating Unreal-side scaffolding.
- JSON is validated strictly using the UPS schema before submission.

