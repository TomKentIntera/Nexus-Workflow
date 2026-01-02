/**
 * Cypress test script for posting to Reddit
 * 
 * This script automates the process of posting content to Reddit with images.
 * IMAGE_URL format: http://127.0.0.1:7860/api/images/runs/{run-id}/{timestamp}.png
 * Configure environment variables for Reddit credentials and content.
 */

describe('Post to Reddit', () => {
  it('should successfully post image to Reddit', () => {
    // Get environment variables
    const redditUsername = Cypress.env('REDDIT_USERNAME');
    const redditPassword = Cypress.env('REDDIT_PASSWORD');
    const postTitle = Cypress.env('POST_TITLE');
    const postDescription = Cypress.env('POST_DESCRIPTION');
    const imageUrl = Cypress.env('IMAGE_URL'); // HTTP URL format: http://127.0.0.1:7860/api/images/runs/{run-id}/{timestamp}.png

    // Validate required environment variables
    if (!redditUsername || !redditPassword) {
      throw new Error('REDDIT_USERNAME and REDDIT_PASSWORD environment variables are required');
    }
    if (!postTitle) {
      throw new Error('POST_TITLE environment variable is required');
    }
    if (!imageUrl) {
      throw new Error('IMAGE_URL environment variable is required');
    }

    // Step 1: Go to reddit.com
    cy.visit('https://www.reddit.com');

    // Step 2: Login
    cy.log('Logging in to Reddit...');
    
    // Navigate directly to login page for more reliable login
    cy.visit('https://www.reddit.com/login', { timeout: 30000 });
    
    // Wait for page to fully load
    cy.url({ timeout: 10000 }).should('include', '/login');
    
    // Wait for the page to be interactive - Reddit uses heavy JS
    cy.window().its('document.readyState').should('eq', 'complete');
    
    // Wait for the login form container to appear
    // Reddit's login form is usually in a specific container
    cy.get('body', { timeout: 15000 }).should('exist');
    
    // Wait a bit more for Reddit's React/JS to fully hydrate the form
    cy.wait(4000);
    
    // Use cy.wrap with document.querySelector to bypass Cypress's query selector issues
    // This directly queries the DOM and wraps the element for Cypress interaction
    cy.window().then((win) => {
      const usernameInput = win.document.querySelector('input[name="username"]');
      if (usernameInput) {
        cy.wrap(usernameInput).focus().clear().type(redditUsername, { force: true, delay: 100 });
      } else {
        throw new Error('Username input not found in DOM');
      }
    });
    
    // Same approach for password
    cy.window().then((win) => {
      const passwordInput = win.document.querySelector('input[name="password"]');
      if (passwordInput) {
        cy.wrap(passwordInput).focus().clear().type(redditPassword, { force: true, delay: 100 });
      } else {
        throw new Error('Password input not found in DOM');
      }
    });
    
    // Click login/submit button
    cy.get('button[type="submit"]', { timeout: 10000 })
      .should('exist')
      .click({ force: true });
    
    // Wait for login to complete - check we're redirected away from login page
    cy.url({ timeout: 20000 }).should('not.include', '/login');
    
    // Wait for page to fully load after login
    cy.wait(2000);
    
    cy.log('Login completed');

    // Step 3: Go to specific subreddit
    cy.log('Navigating to r/InkByTwilight...');
    cy.visit('https://www.reddit.com/r/InkByTwilight/');

    // Step 4: Click "Create Post"
    cy.log('Clicking Create Post...');
    cy.contains('Create Post', { timeout: 10000 })
      .should('be.visible')
      .click({ force: true });

    // Wait for the create post modal/page to load
    cy.url({ timeout: 10000 }).should('include', '/submit');

    // Step 5: Click on "Images"
    cy.log('Selecting Images post type...');
    cy.get('button, a, [role="button"]')
      .contains(/Images?/i)
      .should('be.visible')
      .click({ force: true });

    // Wait for image upload interface to appear
    cy.wait(1000);

    // Step 6: Click on Title input box and input POST_TITLE
    cy.log('Entering post title...');
    cy.get('textarea[placeholder*="title" i], textarea[name*="title" i], input[name*="title" i]', { timeout: 5000 })
      .first()
      .should('be.visible')
      .clear()
      .type(postTitle);

    // Step 7: Download the image from the API endpoint
    // IMAGE_URL format: http://127.0.0.1:7860/api/images/runs/{run-id}/{timestamp}.png
    cy.log(`Downloading image from: ${imageUrl}`);
    
    // Parse IMAGE_URL - could be HTTP URL (preferred) or s3:// path
    let imageDownloadUrl = imageUrl;
    
    // If it's an s3:// URL, convert to MinIO public URL (fallback support)
    if (imageUrl.startsWith('s3://')) {
      // Extract bucket and object name from s3://bucket/path/to/file
      const s3Match = imageUrl.match(/^s3:\/\/([^\/]+)\/(.+)$/);
      if (s3Match) {
        const bucket = s3Match[1];
        const objectPath = s3Match[2];
        // Use MinIO public endpoint or construct URL
        const minioPublicBase = Cypress.env('MINIO_PUBLIC_BASE') || 'http://localhost:9000';
        imageDownloadUrl = `${minioPublicBase}/${bucket}/${objectPath}`;
      }
    }
    // If it's already an HTTP/HTTPS URL, use it directly (expected format)

    // Download image as base64
    cy.request({
      url: imageDownloadUrl,
      encoding: 'base64',
      failOnStatusCode: true,
      timeout: 30000,
      // Handle CORS if needed for localhost URLs
      headers: {
        'Accept': 'image/*'
      }
    }).then((response) => {
      // Determine file extension from URL
      let fileName = 'image.png';
      let mimeType = 'image/png';
      
      // Extract file extension from URL
      const urlMatch = imageUrl.match(/\.(jpg|jpeg|png|gif|webp)$/i);
      if (urlMatch) {
        const ext = urlMatch[1].toLowerCase();
        if (ext === 'jpg' || ext === 'jpeg') {
          fileName = 'image.jpg';
          mimeType = 'image/jpeg';
        } else if (ext === 'gif') {
          fileName = 'image.gif';
          mimeType = 'image/gif';
        } else if (ext === 'webp') {
          fileName = 'image.webp';
          mimeType = 'image/webp';
        } else if (ext === 'png') {
          fileName = 'image.png';
          mimeType = 'image/png';
        }
      }

      // Convert base64 to blob for upload
      const imageBase64 = response.body;

      // Step 8: Click on the "Drag & Drop images" area
      cy.log('Clicking drag & drop area...');
      
      // Look for the drag and drop area - Reddit uses various selectors
      cy.get('div[data-testid="drag-and-drop-zone"], div[class*="drag"], div[class*="drop"], input[type="file"]', { timeout: 5000 })
        .first()
        .then(($dropZone) => {
          if ($dropZone.is('input[type="file"]')) {
            // It's a file input, use selectFile directly
            cy.wrap($dropZone).selectFile(
              {
                contents: Cypress.Buffer.from(imageBase64, 'base64'),
                fileName: fileName,
                mimeType: mimeType,
              },
              { force: true }
            );
          } else {
            // It's a drop zone div, find the file input inside or click to trigger it
            cy.wrap($dropZone).click({ force: true });
            
            // Wait a moment for file picker to appear, then use file input
            cy.wait(500);
            cy.get('input[type="file"]', { timeout: 3000 })
              .first()
              .selectFile(
                {
                  contents: Cypress.Buffer.from(imageBase64, 'base64'),
                  fileName: fileName,
                  mimeType: mimeType,
                },
                { force: true }
              );
          }
        });

      // Wait for image to upload and appear
      cy.log('Waiting for image upload to complete...');
      cy.get('img[src*="blob"], img[src*="data:"], [data-testid="image-preview"]', { timeout: 15000 })
        .should('be.visible');

      // Step 10: Click on the "Body text" textarea
      cy.log('Entering post description...');
      cy.get('textarea[placeholder*="body" i], textarea[placeholder*="text" i], textarea[name*="text" i], textarea[placeholder*="optional" i]', { timeout: 5000 })
        .first()
        .should('be.visible')
        .click({ force: true });

      // Step 11: Input the POST_DESCRIPTION content
      if (postDescription) {
        cy.get('textarea[placeholder*="body" i], textarea[placeholder*="text" i], textarea[name*="text" i], textarea[placeholder*="optional" i]')
          .first()
          .clear()
          .type(postDescription);
      }

      // Step 12: Click Post
      cy.log('Submitting post...');
      cy.get('button:contains("Post"), button[type="submit"]:contains("Post"), button[aria-label*="Post"]', { timeout: 5000 })
        .last()
        .should('be.visible')
        .should('not.be.disabled')
        .click({ force: true });

      // Wait for post to be submitted - URL should change away from /submit
      cy.url({ timeout: 20000 }).should('not.include', '/submit');
      
      // Verify success - check if we're on the post page
      cy.log('Post submitted successfully!');
      cy.wait(2000);
    });
  });
});
