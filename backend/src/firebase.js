const admin = require('firebase-admin');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

try {
  const credPath = process.env.GOOGLE_APPLICATION_CREDENTIALS;
  
  // Check if credentials file exists
  if (credPath && fs.existsSync(path.resolve(credPath))) {
    admin.initializeApp({
      credential: admin.credential.applicationDefault(),
      projectId: process.env.FIREBASE_PROJECT_ID,
    });
    console.log('✓ Firebase Admin SDK initialized successfully');
  } else {
    console.warn('⚠ Firebase credentials file not found at:', credPath);
    console.warn('⚠ Running without Firebase Admin SDK');
    console.warn('⚠ To fix: Download your Firebase service account JSON and place it at:', credPath);
    // Initialize without credentials for development
    admin.initializeApp({
      projectId: process.env.FIREBASE_PROJECT_ID,
    });
  }
} catch (error) {
  console.error('Firebase Admin SDK initialization error:', error);
  console.warn('⚠ Continuing without Firebase Admin SDK...');
}

module.exports = admin;
