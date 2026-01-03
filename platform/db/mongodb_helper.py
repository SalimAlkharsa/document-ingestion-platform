import os
import logging
import pymongo
from pymongo import MongoClient
from datetime import datetime
from typing import List, Dict, Any, Optional
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class MongoDBHelper:
    """Helper class for MongoDB operations related to document embeddings"""

    # Class-level cache for the embedding model
    _embedder = None

    def __init__(self, connection_string=None, db_name=None, collection_name=None):
        """
        Initialize MongoDB connection
        
        Args:
            connection_string: MongoDB connection string (defaults to env variable)
            db_name: MongoDB database name (defaults to env variable or globals)
            collection_name: MongoDB collection name (defaults to env variable or globals)
        """
        # Get connection details from parameters or environment variables
        from globals import MONGO_CONNECTION_STRING, MONGO_DB_NAME, MONGO_EMBEDDINGS_COLLECTION
        
        self.connection_string = connection_string or os.getenv("MONGO_CONNECTION_STRING") or MONGO_CONNECTION_STRING
        self.db_name = db_name or os.getenv("MONGO_DB_NAME") or MONGO_DB_NAME
        self.collection_name = collection_name or os.getenv("MONGO_EMBEDDINGS_COLLECTION") or MONGO_EMBEDDINGS_COLLECTION
        
        # Connect to MongoDB
        try:
            self.client = MongoClient(self.connection_string)
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            
            # Create indexes for better query performance
            # self._create_indexes() --> Dont Need For Now
            
            logger.info(f"Connected to MongoDB: {self.db_name}.{self.collection_name}")
        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {str(e)}")
            raise
    
    def _create_indexes(self):
        """Create necessary indexes for better query performance"""
        try:
            # Create index on document_id for fast lookups
            self.collection.create_index("document_id", unique=True)
            
            # Create index on metadata.file_path
            self.collection.create_index("metadata.file_path")
            
            # Create text index for basic text search capabilities
            self.collection.create_index([
                ("metadata.title", pymongo.TEXT),
                ("metadata.author", pymongo.TEXT)
            ])
            
            logger.debug("MongoDB indexes created or already exist")
        except Exception as e:
            logger.warning(f"Error creating MongoDB indexes: {str(e)}")
    
    def store_embeddings(self, document_id: str, metadata: Dict[str, Any], 
                        embedded_chunks: List[Dict[str, Any]], vector_info: Dict[str, Any]) -> str:
        """
        Store document embeddings in MongoDB
        
        Args:
            document_id: Unique identifier for the document
            metadata: Document metadata
            embedded_chunks: List of chunks with embeddings
            vector_info: Information about the embeddings (dimensions, model, etc.)
            
        Returns:
            MongoDB document ID
        """
        try:
            # Prepare document structure
            document = {
                "document_id": document_id,
                "metadata": metadata,
                "vectors": vector_info,
                "embedded_chunks": embedded_chunks,
                "processing": {
                    "embedding_timestamp": datetime.now().timestamp(),
                    "embedding_time": datetime.now().isoformat(),
                    "storage_type": "mongodb"
                }
            }
            
            # Use upsert to avoid duplicates
            result = self.collection.update_one(
                {"document_id": document_id},
                {"$set": document},
                upsert=True
            )
            
            if result.upserted_id:
                logger.info(f"Inserted new document with ID: {document_id}")
                return str(result.upserted_id)
            else:
                logger.info(f"Updated existing document with ID: {document_id}")
                return document_id
                
        except Exception as e:
            logger.error(f"Error storing embeddings in MongoDB: {str(e)}")
            raise
    
    def get_document_by_id(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by its document_id"""
        return self.collection.find_one({"document_id": document_id})
    
    def get_documents_by_metadata(self, **metadata_filters) -> List[Dict[str, Any]]:
        """Get documents matching metadata filters"""
        query = {}
        for key, value in metadata_filters.items():
            query[f"metadata.{key}"] = value
        
        return list(self.collection.find(query))
    
    def delete_document(self, document_id: str) -> bool:
        """Delete a document by its document_id"""
        result = self.collection.delete_one({"document_id": document_id})
        return result.deleted_count > 0
    
    def count_documents(self) -> int:
        """Count total documents in collection"""
        return self.collection.count_documents({})

    def _get_embedder(self, model_name="all-mpnet-base-v2"):
        """Get or initialize the embedding model (cached at class level)"""
        if MongoDBHelper._embedder is None:
            logger.info(f"Loading embedding model: {model_name}")
            MongoDBHelper._embedder = SentenceTransformer(model_name)
        return MongoDBHelper._embedder

    def search_similar(self, query_text: str, k: int = 5, score_threshold: float = 0.0) -> List[Dict[str, Any]]:
        """
        Search for document chunks similar to the query text using semantic similarity.

        Args:
            query_text: The search query
            k: Number of top results to return
            score_threshold: Minimum similarity score (0.0 to 1.0)

        Returns:
            List of dictionaries containing:
                - text: The chunk text
                - metadata: Full metadata from the chunk
                - score: Cosine similarity score (0.0 to 1.0)
        """
        try:
            # Get the embedding model
            embedder = self._get_embedder()

            # Embed the query text
            logger.debug(f"Embedding query: {query_text[:50]}...")
            query_embedding = embedder.encode(query_text)

            # Fetch all documents from MongoDB
            all_docs = list(self.collection.find({}))
            logger.debug(f"Retrieved {len(all_docs)} documents from MongoDB")

            # Collect all chunks with their similarities
            results = []

            for doc in all_docs:
                # Each document has an array of embedded_chunks
                embedded_chunks = doc.get('embedded_chunks', [])

                for chunk in embedded_chunks:
                    chunk_embedding = np.array(chunk.get('embedding', []))

                    # Skip if embedding is empty or invalid
                    if len(chunk_embedding) == 0:
                        continue

                    # Calculate cosine similarity
                    # cosine_sim = dot(a,b) / (norm(a) * norm(b))
                    similarity = np.dot(query_embedding, chunk_embedding) / (
                        np.linalg.norm(query_embedding) * np.linalg.norm(chunk_embedding)
                    )

                    # Apply threshold filter
                    if similarity >= score_threshold:
                        results.append({
                            'text': chunk.get('text', ''),
                            'metadata': chunk.get('metadata', {}),
                            'score': float(similarity)
                        })

            # Sort by similarity score (descending)
            results.sort(key=lambda x: x['score'], reverse=True)

            # Return top-k results
            top_results = results[:k]

            logger.info(f"Found {len(results)} results, returning top {len(top_results)}")
            return top_results

        except Exception as e:
            logger.error(f"Error in similarity search: {str(e)}")
            raise
