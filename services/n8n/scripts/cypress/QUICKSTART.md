# Quick Start: Running Cypress from n8n

## Quick Setup

### 1. Rebuild n8n Container

After the changes, rebuild the n8n container to install Cypress:

```bash
cd Nexus-Workflow
docker compose build n8n
docker compose up -d n8n
```

### 2. Mount Your Cypress Project (Optional)

If you have a Cypress project, add it to `docker-compose.yml`:

```yaml
services:
  n8n:
    volumes:
      - n8n_data:/home/node/.n8n
      - ./your-cypress-project:/mnt/cypress-project  # Add this line
```

Then restart:
```bash
docker compose up -d n8n
```

### 3. Create n8n Workflow

#### Option A: Using Execute Command Node (Simplest)

1. Add **Execute Command** node
2. Set:
   - **Command:** `python`
   - **Arguments:**
     ```
     /mnt/scripts/cypress/run_tests.py
     --project /mnt/cypress-project
     --headless
     --reporter json
     --output-dir /tmp/cypress-results
     ```
3. Add **Code** node to parse results:
   ```javascript
   const output = JSON.parse($input.item.json.stdout);
   return {
     success: output.success,
     exitCode: output.exit_code,
     results: output.results
   };
   ```

#### Option B: Using Code Node (More Control)

```javascript
const { execSync } = require('child_process');

const projectPath = '/mnt/cypress-project';
const command = `cd ${projectPath} && npx cypress run --headless --reporter json`;

try {
  const output = execSync(command, { 
    encoding: 'utf-8', 
    timeout: 600000,
    cwd: projectPath 
  });
  
  const results = JSON.parse(output);
  return {
    success: true,
    stats: results.stats
  };
} catch (error) {
  return {
    success: false,
    error: error.message
  };
}
```

### 4. Test It

1. Trigger the workflow manually
2. Check the output
3. Review results in `/tmp/cypress-results` (if output-dir was specified)

## Common Use Cases

### Run Specific Test File

```bash
--spec cypress/e2e/login.cy.js
```

### Run with Environment Variables

```bash
--env '{"BASE_URL": "http://localhost:3000", "API_KEY": "secret"}'
```

### Run in Chrome

```bash
--browser chrome --headless
```

### Get JUnit XML for CI/CD

```bash
--reporter junit --reporter-options '{"mochaFile": "/tmp/results.xml"}'
```

## Next Steps

See [README.md](./README.md) for detailed documentation.


