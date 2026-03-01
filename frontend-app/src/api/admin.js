import api from "./axios";

export const adminIngestFiles = async (files, { onUploadProgress } = {}) => {
  if (!Array.isArray(files) || files.length === 0) {
    throw new Error("Select at least one PDF file");
  }

  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });

  try {
    const response = await api.post("/admin/ingest/upload", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
      timeout: 30 * 60 * 1000,
      onUploadProgress,
    });
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Ingestion failed" };
  }
};

export const listIngestedDocuments = async () => {
  try {
    const response = await api.get("/admin/documents");
    return response.data?.documents || [];
  } catch (error) {
    throw error.response?.data || { error: "Could not load ingested documents" };
  }
};

export const fetchAdminStatistics = async () => {
  try {
    const response = await api.get("/admin/statistics");
    return response.data?.statistics || {};
  } catch (error) {
    throw error.response?.data || { error: "Could not load admin statistics" };
  }
};

export const deleteIngestedDocument = async (docId) => {
  try {
    if (!docId || !String(docId).trim()) {
      throw new Error("Document ID is required");
    }
    const response = await api.delete(`/admin/documents/${encodeURIComponent(docId)}`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Could not delete ingested document" };
  }
};

export const bulkDeleteIngestedDocuments = async (docIds) => {
  try {
    if (!Array.isArray(docIds) || docIds.length === 0) {
      throw new Error("At least one document ID is required");
    }
    const cleaned = docIds
      .map((docId) => String(docId || "").trim())
      .filter(Boolean);
    if (cleaned.length === 0) {
      throw new Error("At least one valid document ID is required");
    }

    const response = await api.post("/admin/documents/bulk-delete", { doc_ids: cleaned });
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Could not delete selected documents" };
  }
};

export const retrieveChunksForVerification = async ({
  query,
  mode = "hybrid",
  top_k = 8,
  initial_k = null,
  filters = null,
}) => {
  try {
    if (!query || !query.trim()) {
      throw new Error("Query is required");
    }

    const payload = {
      query: query.trim(),
      mode,
      top_k,
    };

    if (initial_k != null) payload.initial_k = initial_k;
    if (filters && typeof filters === "object") payload.filters = filters;

    const response = await api.post("/admin/retrieve-chunks", payload);
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: "Could not retrieve chunks for verification" };
  }
};
