/**
 * Cypress test script for posting to Patreon
 * 
 * This script automates the process of posting content to Patreon.
 * Configure environment variables for Patreon credentials and content.
 */

describe('Post to Patreon', () => {
  beforeEach(() => {
    // Set base URL from environment variable or use default
    cy.visit(Cypress.env('PATREON_URL') || 'https://www.patreon.com');
  });

  it('should successfully post content to Patreon', () => {
    // Login to Patreon
    const patreonEmail = Cypress.env('PATREON_EMAIL');
    const patreonPassword = Cypress.env('PATREON_PASSWORD');

    if (!patreonEmail || !patreonPassword) {
      throw new Error('PATREON_EMAIL and PATREON_PASSWORD environment variables are required');
    }

    // Click on login if not already logged in
    cy.get('body').then(($body) => {
      if ($body.text().includes('Log in') || $body.text().includes('Sign in')) {
        cy.contains('Log in').click({ force: true });
        
        // Enter credentials
        cy.get('input[type="email"], input[name="email"], input[id*="email"]').first().type(patreonEmail);
        cy.get('input[type="password"], input[name="password"], input[id*="password"]').first().type(patreonPassword);
        
        // Submit login form
        cy.get('button[type="submit"], button:contains("Log in"), button:contains("Sign in")').first().click();
        
        // Wait for login to complete
        cy.url().should('not.include', '/login', { timeout: 10000 });
      }
    });

    // Navigate to post creation page
    // Adjust selectors based on Patreon's actual UI
    cy.get('body').then(($body) => {
      if ($body.find('a:contains("Post"), button:contains("Create post"), [data-testid*="post"]').length > 0) {
        cy.contains('Post').first().click({ force: true });
      } else {
        // Alternative: navigate directly to post URL
        cy.visit(Cypress.env('PATREON_POST_URL') || 'https://www.patreon.com/posts/new');
      }
    });

    // Get content from environment or use defaults
    const postTitle = Cypress.env('POST_TITLE') || 'New Post';
    const postContent = Cypress.env('POST_CONTENT') || 'This is a test post from Cypress automation.';
    const imageUrl = Cypress.env('IMAGE_URL');

    // Fill in post title
    cy.get('textarea, input[placeholder*="title" i], input[name*="title" i]').first().should('be.visible').type(postTitle);

    // Fill in post content
    cy.get('textarea[placeholder*="post" i], textarea[name*="content" i], [contenteditable="true"]').first().should('be.visible').type(postContent);

    // Upload image if provided
    if (imageUrl) {
      cy.get('input[type="file"], button:contains("Image"), button:contains("Upload")').first().then(($input) => {
        if ($input.is('input[type="file"]')) {
          // If it's a file input, we'll need to download and upload
          cy.request({
            url: imageUrl,
            encoding: 'base64'
          }).then((response) => {
            cy.fixture('test-image.png', 'base64').then((fileContent) => {
              // Create blob and upload
              // Note: This may need adjustment based on Patreon's upload mechanism
              cy.get('input[type="file"]').first().selectFile({
                contents: Cypress.Buffer.from(response.body, 'base64'),
                fileName: 'image.png',
                mimeType: 'image/png'
              }, { force: true });
            });
          });
        } else {
          // Alternative: paste image URL
          cy.get('button:contains("Image"), button:contains("Upload")').first().click();
          cy.get('input[type="url"], input[placeholder*="url" i]').first().type(imageUrl);
          cy.contains('Add', 'button').click();
        }
      });
    }

    // Publish post
    cy.get('button:contains("Publish"), button:contains("Post"), button[type="submit"]').last().click();

    // Verify success
    cy.contains('Published', 'Post created', 'Success', { timeout: 15000 }).should('be.visible');
    
    // Wait a moment for the post to be created
    cy.wait(2000);
  });

  it('should handle posting with custom content', () => {
    // This test can be customized for specific posting scenarios
    cy.log('Custom posting scenario');
    
    // Add your custom posting logic here
    const customContent = Cypress.env('CUSTOM_POST_CONTENT');
    if (customContent) {
      cy.log(`Posting custom content: ${customContent}`);
    }
  });
});


