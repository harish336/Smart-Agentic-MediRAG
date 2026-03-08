import api from "./axios";

/**
 * Ask question to backend /chat/ask endpoint
 * Automatically uses JWT from axios interceptor
 */
export const askQuestion = async ({
  query,
  thread_id = null,
  query_mode = "fast",
  upload_ids = [],
  user_message_meta = null,
  thread_messages = [],
  rewrite_from_message_id = "",
  agent_hint = "",
  signal,
}) => {
  try {
    if (!query) {
      throw new Error("Query is required");
    }

    const response = await api.post(
      "/chat/ask",
      {
        query,
        thread_id,
        query_mode,
        upload_ids,
        user_message_meta,
        thread_messages,
        rewrite_from_message_id: rewrite_from_message_id || "",
        agent_hint: agent_hint || "",
      },
      { signal }
    );

    return response.data;

  } catch (error) {
    if (error?.code === "ERR_CANCELED" || error?.name === "CanceledError") {
      throw { canceled: true, message: "Generation stopped" };
    }
    console.error("Ask Question Error:", error);

    // If backend returned error message
    if (error.response?.data) {
      throw error.response.data;
    }

    throw {
      error: "Network error",
      message: "Unable to connect to server"
    };
  }
};


/**
 * Retrieve documents (optional usage)
 */
export const retrieveDocuments = async ({
  query,
  mode = "hybrid",
  top_k = 5
}) => {
  try {
    if (!query) {
      throw new Error("Query is required");
    }

    const response = await api.post("/retrieve", {
      query,
      mode,
      top_k
    });

    return response.data;

  } catch (error) {
    console.error("Retrieve Error:", error);

    if (error.response?.data) {
      throw error.response.data;
    }

    throw {
      error: "Network error",
      message: "Unable to connect to server"
    };
  }
};

export const uploadChatFiles = async ({
  files,
  index = false,
  thread_id = null,
}) => {
  if (!Array.isArray(files) || files.length === 0) {
    throw new Error("Select at least one file");
  }

  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  formData.append("index", index ? "true" : "false");
  if (thread_id) formData.append("thread_id", thread_id);

  try {
    const response = await api.post("/chat/uploads", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 10 * 60 * 1000,
    });
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Upload failed" };
  }
};

export const listChatUploads = async ({ thread_id = null, limit = 50 } = {}) => {
  try {
    const params = { limit };
    if (thread_id) params.thread_id = thread_id;
    const response = await api.get("/chat/uploads", { params });
    return response.data?.uploads || [];
  } catch (error) {
    throw error.response?.data || { error: "Could not load uploads" };
  }
};

export const deleteChatUpload = async (uploadId) => {
  try {
    if (!uploadId || !String(uploadId).trim()) {
      throw new Error("uploadId is required");
    }
    const response = await api.delete(`/chat/uploads/${encodeURIComponent(uploadId)}`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Could not cancel upload" };
  }
};

export const fetchChatUploadBlob = async (uploadId) => {
  try {
    if (!uploadId || !String(uploadId).trim()) {
      throw new Error("uploadId is required");
    }
    const response = await api.get(`/chat/uploads/${encodeURIComponent(uploadId)}/file`, {
      responseType: "blob",
    });
    return response.data;
  } catch (error) {
    if (error.response?.data) {
      throw error.response.data;
    }
    throw { error: "Network error", message: "Unable to load uploaded file" };
  }
};

export const listThreads = async () => {
  try {
    const response = await api.get("/chat/threads");
    return response.data?.threads || [];
  } catch (error) {
    if (error.response?.data) {
      throw error.response.data;
    }
    throw { error: "Network error", message: "Unable to load threads" };
  }
};

export const fetchCitationPdfBlob = async (docId) => {
  try {
    if (!docId || !String(docId).trim()) {
      throw new Error("Document ID is required");
    }
    const response = await api.get(`/chat/citations/${encodeURIComponent(docId)}/pdf`, {
      responseType: "blob",
    });
    return response.data;
  } catch (error) {
    if (error.response?.data) {
      throw error.response.data;
    }
    throw { error: "Network error", message: "Unable to load citation PDF" };
  }
};

export const listThreadMessages = async (threadId) => {
  try {
    const response = await api.get(`/chat/messages/${threadId}`);
    return response.data?.messages || [];
  } catch (error) {
    if (error.response?.data) {
      throw error.response.data;
    }
    throw { error: "Network error", message: "Unable to load messages" };
  }
};

export const deleteThread = async (threadId) => {
  try {
    const response = await api.delete(`/chat/threads/${threadId}`);
    return response.data;
  } catch (error) {
    if (error.response?.data) {
      throw error.response.data;
    }
    throw { error: "Network error", message: "Unable to delete thread" };
  }
};

export const saveCanvasEdit = async (threadId, content) => {
  try {
    if (!threadId) throw new Error("threadId is required");
    if (!content || !content.trim()) throw new Error("content is required");
    const response = await api.put(`/chat/canvas/${threadId}`, { content });
    return response.data;
  } catch (error) {
    if (error.response?.data) {
      throw error.response.data;
    }
    throw { error: "Network error", message: "Unable to save canvas edit" };
  }
};
