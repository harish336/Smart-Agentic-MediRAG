import api from "./axios";

/**
 * Ask question to backend /answer endpoint
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

    const response = await api.post("/answer", {
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