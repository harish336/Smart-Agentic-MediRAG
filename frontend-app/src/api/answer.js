import api from "./axios";

/**
 * Ask question to backend /chat/ask endpoint
 * Automatically uses JWT from axios interceptor
 */
export const askQuestion = async ({
  query,
  thread_id = null
}) => {
  try {
    if (!query) {
      throw new Error("Query is required");
    }

    const response = await api.post("/chat/ask", {
      query,
      thread_id
    });

    return response.data;

  } catch (error) {
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
