const express = require('express');
const router = express.Router();
const axios = require('axios');
const multer = require('multer');
const verifySession = require('../middleware/verifySession');

const MCP_SERVER_URL = process.env.MCP_SERVER_URL || 'http://127.0.0.1:8000';

// Configure multer for file uploads
const upload = multer({ storage: multer.memoryStorage() });

// Create ML project via chat
router.post('/ml/chat', verifySession, async (req, res) => {
  try {
    const { message } = req.body;
    const firebaseUid = req.user.uid;
    const userName = req.user.name || req.user.email;
    const userEmail = req.user.email;

    console.log(`ML Chat request from user ${firebaseUid}: ${message}`);

    // Forward to MCP server's planner agent endpoint
    const mcpResponse = await axios.post(`${MCP_SERVER_URL}/api/ml/planner`, {
      user_id: firebaseUid,
      message,
      user_name: userName,
      user_email: userEmail
    });

    res.json(mcpResponse.data);
  } catch (error) {
    console.error('Error in ML chat:', error.message);
    res.status(500).json({ 
      error: 'Failed to process ML request',
      details: error.response?.data || error.message 
    });
  }
});

// Get all ML projects for user (admin can fetch all with ?all=true)
router.get('/ml/projects', verifySession, async (req, res) => {
  try {
    const firebaseUid = req.user.uid;
    const fetchAll = req.query.all || 'false';
    
    console.log(`Fetching ML projects for user ${firebaseUid} (all=${fetchAll})`);

    const mcpResponse = await axios.get(`${MCP_SERVER_URL}/api/ml/projects`, {
      params: { user_id: firebaseUid, all: fetchAll }
    });

    res.json(mcpResponse.data);
  } catch (error) {
    console.error('Error fetching ML projects:', error.message);
    res.status(500).json({ 
      error: 'Failed to fetch projects',
      details: error.response?.data || error.message 
    });
  }
});

// Get specific ML project by ID
router.get('/ml/projects/:projectId', verifySession, async (req, res) => {
  try {
    const { projectId } = req.params;
    const firebaseUid = req.user.uid;

    console.log(`Fetching project ${projectId} for user ${firebaseUid}`);

    const mcpResponse = await axios.get(`${MCP_SERVER_URL}/api/ml/projects/${projectId}`, {
      params: { user_id: firebaseUid }
    });

    res.json(mcpResponse.data);
  } catch (error) {
    console.error('Error fetching project:', error.message);
    res.status(500).json({ 
      error: 'Failed to fetch project',
      details: error.response?.data || error.message 
    });
  }
});

// Get project logs
router.get('/ml/projects/:projectId/logs', verifySession, async (req, res) => {
  try {
    const { projectId } = req.params;
    const firebaseUid = req.user.uid;

    console.log(`Fetching logs for project ${projectId}`);

    const mcpResponse = await axios.get(`${MCP_SERVER_URL}/api/ml/projects/${projectId}/logs`, {
      params: { user_id: firebaseUid }
    });

    res.json(mcpResponse.data);
  } catch (error) {
    console.error('Error fetching project logs:', error.message);
    res.status(500).json({ 
      error: 'Failed to fetch logs',
      details: error.response?.data || error.message 
    });
  }
});

// Download model
router.get('/ml/projects/:projectId/download', verifySession, async (req, res) => {
  try {
    const { projectId } = req.params;
    const firebaseUid = req.user.uid;

    console.log(`Downloading model for project ${projectId}`);

    const mcpResponse = await axios.get(`${MCP_SERVER_URL}/api/ml/projects/${projectId}/download`, {
      params: { user_id: firebaseUid },
      responseType: 'stream'
    });

    // Forward the stream to client
    res.setHeader('Content-Type', mcpResponse.headers['content-type'] || 'application/zip');
    res.setHeader('Content-Disposition', mcpResponse.headers['content-disposition'] || 'attachment; filename=model.zip');
    mcpResponse.data.pipe(res);
  } catch (error) {
    console.error('Error downloading model:', error.message);
    
    // Don't try to JSON.stringify the error response if it's a stream
    const errorMessage = error.response?.status === 404 
      ? 'Model not found or not ready for download'
      : error.response?.status === 403
      ? 'Access denied'
      : 'Failed to download model';
    
    res.status(error.response?.status || 500).json({ 
      error: errorMessage,
      details: error.message 
    });
  }
});

// Admin endpoints
router.get('/admin/stats', verifySession, async (req, res) => {
  try {
    const firebaseUid = req.user.uid;
    
    const mcpResponse = await axios.get(`${MCP_SERVER_URL}/api/admin/stats`, {
      params: { user_id: firebaseUid }
    });
    
    res.json(mcpResponse.data);
  } catch (error) {
    console.error('Error fetching admin stats:', error.message);
    res.status(error.response?.status || 500).json({ 
      error: 'Failed to fetch admin stats',
      details: error.response?.data || error.message 
    });
  }
});

router.get('/admin/users', verifySession, async (req, res) => {
  try {
    const firebaseUid = req.user.uid;
    
    const mcpResponse = await axios.get(`${MCP_SERVER_URL}/api/admin/users`, {
      params: { user_id: firebaseUid }
    });
    
    res.json(mcpResponse.data);
  } catch (error) {
    console.error('Error fetching users:', error.message);
    res.status(error.response?.status || 500).json({ 
      error: 'Failed to fetch users',
      details: error.response?.data || error.message 
    });
  }
});

router.get('/admin/projects', verifySession, async (req, res) => {
  try {
    const firebaseUid = req.user.uid;
    const limit = req.query.limit || 50;
    
    const mcpResponse = await axios.get(`${MCP_SERVER_URL}/api/admin/projects`, {
      params: { user_id: firebaseUid, limit }
    });
    
    res.json(mcpResponse.data);
  } catch (error) {
    console.error('Error fetching projects:', error.message);
    res.status(error.response?.status || 500).json({ 
      error: 'Failed to fetch projects',
      details: error.response?.data || error.message 
    });
  }
});

router.get('/admin/logs', verifySession, async (req, res) => {
  try {
    const firebaseUid = req.user.uid;
    const limit = req.query.limit || 100;
    
    const mcpResponse = await axios.get(`${MCP_SERVER_URL}/api/admin/logs`, {
      params: { user_id: firebaseUid, limit }
    });
    
    res.json(mcpResponse.data);
  } catch (error) {
    console.error('Error fetching logs:', error.message);
    res.status(error.response?.status || 500).json({ 
      error: 'Failed to fetch logs',
      details: error.response?.data || error.message 
    });
  }
});

// Test model with image
router.post('/ml/projects/:projectId/test', verifySession, upload.single('image'), async (req, res) => {
  try {
    const { projectId } = req.params;
    const firebaseUid = req.user.uid;

    console.log(`Testing model for project ${projectId}`);

    if (!req.file) {
      return res.status(400).json({ error: 'No image file uploaded' });
    }

    // Forward file to MCP server
    const FormData = require('form-data');
    const formData = new FormData();
    
    formData.append('file', req.file.buffer, req.file.originalname);
    formData.append('user_id', firebaseUid);

    const mcpResponse = await axios.post(
      `${MCP_SERVER_URL}/api/ml/projects/${projectId}/test`,
      formData,
      {
        headers: {
          ...formData.getHeaders()
        }
      }
    );

    res.json(mcpResponse.data);
  } catch (error) {
    console.error('Error testing model:', error.message);
    res.status(500).json({ 
      error: 'Failed to test model',
      details: error.response?.data?.detail || error.message 
    });
  }
});

// Upload custom dataset for quick training
const datasetUpload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 500 * 1024 * 1024 } // 500MB limit
});

router.post('/ml/upload-dataset', verifySession, datasetUpload.single('dataset'), async (req, res) => {
  try {
    const firebaseUid = req.user.uid;
    const userName = req.user.name || req.user.email;
    const userEmail = req.user.email;

    console.log(`Dataset upload request from user ${firebaseUid}`);

    if (!req.file) {
      return res.status(400).json({ error: 'No dataset file uploaded' });
    }

    const { project_name, task_type, preferred_model, description } = req.body;

    if (!project_name || !project_name.trim()) {
      return res.status(400).json({ error: 'Project name is required' });
    }

    console.log(`Uploading dataset: ${req.file.originalname} (${(req.file.size / (1024 * 1024)).toFixed(1)}MB)`);

    // Forward to MCP server
    const FormData = require('form-data');
    const formData = new FormData();

    formData.append('dataset', req.file.buffer, {
      filename: req.file.originalname,
      contentType: req.file.mimetype
    });
    formData.append('user_id', firebaseUid);
    formData.append('project_name', project_name.trim());
    formData.append('task_type', task_type || 'image_classification');
    formData.append('preferred_model', preferred_model || 'resnet18');
    formData.append('description', description || '');
    formData.append('user_name', userName || '');
    formData.append('user_email', userEmail || '');

    const mcpResponse = await axios.post(
      `${MCP_SERVER_URL}/api/ml/upload-dataset`,
      formData,
      {
        headers: {
          ...formData.getHeaders()
        },
        maxContentLength: 600 * 1024 * 1024,
        maxBodyLength: 600 * 1024 * 1024,
        timeout: 300000 // 5 minute timeout
      }
    );

    console.log(`Dataset upload successful for project: ${mcpResponse.data.projectId}`);
    res.json(mcpResponse.data);
  } catch (error) {
    console.error('Error uploading dataset:', error.message);
    res.status(error.response?.status || 500).json({
      error: 'Failed to upload dataset',
      details: error.response?.data?.detail || error.message
    });
  }
});

module.exports = router;
