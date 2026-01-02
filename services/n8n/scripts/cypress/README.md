# Running Cypress Tests from n8n

This guide explains how to run Cypress tests from n8n workflows.

## Overview

There are several ways to run Cypress tests from n8n:

1. **Python Script Wrapper** (Recommended) - Use the `run_tests.py` script via Execute Command node
2. **Execute Command Node** - Run Cypress CLI directly
3. **Code Node (JavaScript)** - Run Cypress programmatically using Node.js

## Prerequisites

- Cypress is installed in the n8n container (handled by Dockerfile)
- Your Cypress project should be accessible from the n8n container (via volume mount or shared filesystem)

## Method 1: Using Python Script Wrapper (Recommended)

The `run_tests.py` script provides a convenient way to run Cypress tests with structured output.

### Setup in n8n

1. **Add an Execute Command node** to your n8n workflow
2. **Configure the node:**
   - **Command:** `/usr/local/bin/python` (or `python3`)
   - **Arguments:**
     ```
     /mnt/scripts/cypress/run_tests.py
     --project /path/to/cypress/project
     --spec cypress/e2e/my-test.cy.js
     --browser electron
     --headless
     --output-dir /tmp/cypress-results
     --reporter json
     ```

### Parameters

- `--project`: Path to Cypress project directory (required if not running from project root)
- `--spec`: Path to specific test file (optional, runs all tests if omitted)
- `--browser`: Browser to use (`electron`, `chrome`, `chromium`, `firefox`, `edge`)
- `--headless` / `--headed`: Run mode (default: headless)
- `--output-dir`: Directory to save results, screenshots, and videos
- `--reporter`: Reporter format (`json`, `junit`, `spec`, `mochawesome`)
- `--env`: JSON string of environment variables (e.g., `'{"BASE_URL": "http://localhost:3000"}'`)
- `--config`: Path to custom cypress.config.js file

### Example n8n Workflow

```
1. Manual Trigger
2. Execute Command Node
   - Command: python
   - Arguments: 
     /mnt/scripts/cypress/run_tests.py
     --project {{ $json.project_path }}
     --spec {{ $json.test_file }}
     --browser electron
     --headless
     --output-dir /tmp/cypress-results
     --reporter json
3. Code Node (JavaScript)
   - Parse the JSON output to extract test results
   - Example:
     ```javascript
     const output = JSON.parse($input.item.json.stdout);
     if (!output.success) {
       throw new Error(`Cypress tests failed: ${output.stderr}`);
     }
     return { success: true, results: output.results };
     ```
4. Conditional Node
   - Check if tests passed
   - Route to success/failure actions
```

### Output Format

The script returns JSON with:

```json
{
  "exit_code": 0,
  "success": true,
  "stdout": "Cypress test output...",
  "stderr": "",
  "command": "npx cypress run ...",
  "results": {
    "json": { /* Cypress JSON results */ },
    "screenshots": ["/path/to/screenshot.png"],
    "videos": ["/path/to/video.mp4"]
  }
}
```

## Method 2: Execute Command Node (Direct)

You can run Cypress directly using the Execute Command node:

1. **Add Execute Command node**
2. **Configure:**
   - **Command:** `npx`
   - **Arguments:**
     ```
     cypress
     run
     --project /path/to/cypress/project
     --spec cypress/e2e/my-test.cy.js
     --browser electron
     --headless
     --reporter json
     --reporter-options '{"output": "/tmp/results.json"}'
     ```

## Method 3: Code Node (JavaScript)

For more control, use the Code node with JavaScript:

```javascript
const { execSync } = require('child_process');
const path = require('path');

const projectPath = $input.item.json.project_path || '/path/to/cypress/project';
const spec = $input.item.json.spec || null;
const browser = $input.item.json.browser || 'electron';

let command = `cd ${projectPath} && npx cypress run --browser ${browser} --headless --reporter json`;

if (spec) {
  command += ` --spec ${spec}`;
}

try {
  const output = execSync(command, { encoding: 'utf-8', timeout: 600000 });
  const results = JSON.parse(output);
  
  return {
    success: true,
    results: results,
    passed: results.stats.passes,
    failed: results.stats.failures
  };
} catch (error) {
  return {
    success: false,
    error: error.message,
    stdout: error.stdout,
    stderr: error.stderr
  };
}
```

## Docker Volume Mounting

To access your Cypress project from the n8n container, you can mount it as a volume in `docker-compose.yml`:

```yaml
services:
  n8n:
    volumes:
      - n8n_data:/home/node/.n8n
      - ./cypress-project:/mnt/cypress-project:ro  # Read-only mount
      # Or for read-write:
      # - ./cypress-project:/mnt/cypress-project
```

Then use `/mnt/cypress-project` as your `--project` path.

## Environment Variables

Pass environment variables to Cypress tests:

### Using Python Script

```bash
--env '{"BASE_URL": "http://localhost:3000", "API_KEY": "secret"}'
```

### Using Execute Command

```bash
BASE_URL=http://localhost:3000 npx cypress run ...
```

### In Cypress Config

You can also configure environment variables in `cypress.config.js`:

```javascript
export default defineConfig({
  e2e: {
    env: {
      BASE_URL: process.env.BASE_URL || 'http://localhost:3000'
    }
  }
});
```

## Complete Example Workflow

```
1. Manual Trigger / Schedule Trigger
   └─> Input: { project_path: "/mnt/cypress-project", test_file: "cypress/e2e/login.cy.js" }

2. Execute Command
   └─> Run: python /mnt/scripts/cypress/run_tests.py --project {{ $json.project_path }} --spec {{ $json.test_file }} --headless --output-dir /tmp/cypress-results --reporter json

3. Code Node (Parse Results)
   └─> Extract test results from JSON output

4. IF Node
   ├─> IF tests passed
   │   └─> HTTP Request: POST to Slack webhook (success notification)
   └─> ELSE
       └─> HTTP Request: POST to Slack webhook (failure notification with screenshots)
```

## Troubleshooting

### Cypress not found

If you see "Cypress not found", ensure:
- Cypress is installed: `npm install -g cypress` (in Dockerfile)
- Or install it per-project: `cd /path/to/project && npm install cypress`

### Permission errors

Ensure the n8n user has access to the Cypress project directory:
```bash
chmod -R 755 /path/to/cypress-project
```

### Browser issues

If browser fails to launch:
- Install required dependencies in Dockerfile
- For headless Chrome: May need additional system packages
- Check Cypress logs in stderr output

### Timeout errors

Increase timeout in the Execute Command node or script execution timeout in n8n settings.

## Tips

1. **Use JSON reporter** for easy parsing in n8n
2. **Save outputs to `/tmp`** for easy access (gets cleaned on container restart)
3. **Use environment variables** to make tests configurable
4. **Parse results in Code node** to make workflow decisions
5. **Upload screenshots/videos** to MinIO or another storage service for later review

