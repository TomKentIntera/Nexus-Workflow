// ***********************************************
// This example commands.js shows you how to
// create various custom commands and overwrite
// existing commands.
//
// For more comprehensive examples of custom
// commands please read more here:
// https://on.cypress.io/custom-commands
// ***********************************************

// Custom command to login to Reddit
Cypress.Commands.add('loginToReddit', (username, password) => {
  cy.visit('https://www.reddit.com');
  cy.contains('Log In').click();
  cy.get('input[name="username"]').type(username);
  cy.get('input[name="password"]').type(password);
  cy.get('button[type="submit"]').first().click();
  cy.url().should('not.include', '/login', { timeout: 10000 });
});

// Custom command to login to Patreon
Cypress.Commands.add('loginToPatreon', (email, password) => {
  cy.visit('https://www.patreon.com');
  cy.contains('Log in').click({ force: true });
  cy.get('input[type="email"]').first().type(email);
  cy.get('input[type="password"]').first().type(password);
  cy.get('button[type="submit"]').first().click();
  cy.url().should('not.include', '/login', { timeout: 10000 });
});

// Custom command to wait for element with retry
Cypress.Commands.add('waitForElement', (selector, options = {}) => {
  const timeout = options.timeout || 10000;
  cy.get(selector, { timeout }).should('be.visible');
});

// Custom command to upload image from URL
Cypress.Commands.add('uploadImageFromUrl', (imageUrl, fileInputSelector) => {
  cy.request({
    url: imageUrl,
    encoding: 'base64'
  }).then((response) => {
    cy.get(fileInputSelector).selectFile({
      contents: Cypress.Buffer.from(response.body, 'base64'),
      fileName: 'image.png',
      mimeType: 'image/png'
    }, { force: true });
  });
});

