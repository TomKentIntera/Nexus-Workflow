require('dotenv').config();

const { defineConfig } = require('cypress');

module.exports = defineConfig({
  e2e: {
    setupNodeEvents(on, config) {
      // implement node event listeners here
    },
    baseUrl: 'https://www.reddit.com',
    // Default viewport size
    viewportWidth: 1280,
    viewportHeight: 720,
    // Default timeout
    defaultCommandTimeout: 10000,
    // Request timeout
    requestTimeout: 10000,
    // Response timeout
    responseTimeout: 10000,
    // Page load timeout
    pageLoadTimeout: 30000,
    // Screenshot on failure
    screenshotOnRunFailure: true,
    // Video recording
    video: true,
    // Support files
    supportFile: 'cypress/support/e2e.js',
    // Spec pattern
    specPattern: 'cypress/e2e/**/*.js',
    // Environment variables
    env: {
      // Reddit configuration
      REDDIT_URL: process.env.REDDIT_URL || 'https://www.reddit.com',
      REDDIT_USERNAME: process.env.REDDIT_USERNAME,
      REDDIT_PASSWORD: process.env.REDDIT_PASSWORD,
      REDDIT_SUBREDDIT: process.env.REDDIT_SUBREDDIT || 'test',
      REDDIT_AUTO_SUBMIT: process.env.REDDIT_AUTO_SUBMIT || 'true',
      // Patreon configuration
      PATREON_URL: process.env.PATREON_URL || 'https://www.patreon.com',
      PATREON_EMAIL: process.env.PATREON_EMAIL,
      PATREON_PASSWORD: process.env.PATREON_PASSWORD,
      PATREON_POST_URL: process.env.PATREON_POST_URL,
      // Post content
      POST_TITLE: process.env.POST_TITLE,
      POST_CONTENT: process.env.POST_CONTENT,
      POST_DESCRIPTION: process.env.POST_DESCRIPTION,
      POST_TYPE: process.env.POST_TYPE || 'text', // 'text', 'link', or 'image'
      IMAGE_URL: process.env.IMAGE_URL,
      LINK_URL: process.env.LINK_URL,
      CUSTOM_POST_CONTENT: process.env.CUSTOM_POST_CONTENT,
      // MinIO configuration
      MINIO_PUBLIC_BASE: process.env.MINIO_PUBLIC_BASE || 'http://localhost:9000',
    },
  },
});

