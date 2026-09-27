import axios from 'axios';

const mlApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  withCredentials: true,
});

// ML Project endpoints
export const createMLProject = (message) => {
  return mlApi.post('/api/ml/chat', { message });
};

export const getMLProjects = () => {
  return mlApi.get('/api/ml/projects');
};

// Admin: fetch all projects from all users
export const getAllMLProjects = () => {
  return mlApi.get('/api/ml/projects', { params: { all: 'true' } });
};

export const getMLProjectById = (projectId) => {
  return mlApi.get(`/api/ml/projects/${projectId}`);
};

export const getProjectLogs = (projectId) => {
  return mlApi.get(`/api/ml/projects/${projectId}/logs`);
};

export const downloadModel = (projectId) => {
  return mlApi.get(`/api/ml/projects/${projectId}/download`, {
    responseType: 'blob'
  });
};

export const testModel = (projectId, imageFile) => {
  const formData = new FormData();
  formData.append('image', imageFile);
  return mlApi.post(`/api/ml/projects/${projectId}/test`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  });
};

// Upload custom dataset for quick training
export const uploadCustomDataset = (formData, onUploadProgress) => {
  return mlApi.post('/api/ml/upload-dataset', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    },
    onUploadProgress,
    timeout: 300000 // 5 minute timeout for large uploads
  });
};

// Sanity Agent: approve/skip fix actions (Human-in-the-Loop)
export const approveSanityActions = (projectId, actions) => {
  return mlApi.post(`/api/ml/projects/${projectId}/sanity-approve`, { actions });
};

// Trainer Agent: save training configuration (Human-in-the-Loop)
export const saveTrainingConfig = (projectId, config) => {
  return mlApi.post(`/api/ml/projects/${projectId}/training-config`, config);
};

export default mlApi;
