#!/usr/bin/env python3
"""
Streamlit Demo Application for Document Retrieval
Demonstrates semantic search over embedded documents in MongoDB
"""
import streamlit as st
import sys
from pathlib import Path
import os

# Add project root and platform to sys.path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'platform'))

from db.mongodb_helper import MongoDBHelper
import re
from sentence_transformers import SentenceTransformer
import numpy as np

# Page configuration
st.set_page_config(
    page_title="Document Search Demo",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize MongoDB helper with caching
@st.cache_resource
def get_mongo_helper():
    """Initialize and cache MongoDB helper"""
    return MongoDBHelper()

# Initialize embedding model for highlighting
@st.cache_resource
def get_embedder():
    """Initialize and cache the embedding model for sentence highlighting"""
    return SentenceTransformer("all-mpnet-base-v2")

def get_database_stats(mongo_helper):
    """Get statistics about the database"""
    try:
        total_docs = mongo_helper.count_documents()

        # Get all documents to calculate stats
        all_docs = list(mongo_helper.collection.find({}))

        # Count unique source documents
        unique_files = set()
        total_chunks = 0

        for doc in all_docs:
            embedded_chunks = doc.get('embedded_chunks', [])
            total_chunks += len(embedded_chunks)

            for chunk in embedded_chunks:
                metadata = chunk.get('metadata', {})
                file_path = metadata.get('file_path', '')
                if file_path:
                    unique_files.add(file_path)

        return {
            'total_documents': total_docs,
            'total_chunks': total_chunks,
            'unique_files': len(unique_files),
            'files': list(unique_files)
        }
    except Exception as e:
        st.error(f"Error getting database stats: {str(e)}")
        return None

def display_sidebar(mongo_helper):
    """Display sidebar with database statistics"""
    st.sidebar.title("📊 Database Info")

    stats = get_database_stats(mongo_helper)

    if stats:
        st.sidebar.metric("MongoDB Documents", stats['total_documents'])
        st.sidebar.metric("Total Chunks", stats['total_chunks'])
        st.sidebar.metric("Source PDFs", stats['unique_files'])

        st.sidebar.divider()

        st.sidebar.subheader("🤖 Embedding Model")
        st.sidebar.info("**all-mpnet-base-v2**\n\n768 dimensions\nSentence Transformer\n\nHigh-quality embeddings for better search accuracy")

        st.sidebar.divider()

        st.sidebar.subheader("📄 Source Files")
        for file_path in stats['files']:
            filename = os.path.basename(file_path)
            st.sidebar.text(f"• {filename}")

def clean_text(text):
    """Clean text from Docling markup and formatting issues"""
    if not text:
        return ""

    # Remove Docling markup tags like [<Paragraph>, <RawText>, etc.]
    text = re.sub(r'\[<[^>]+>\s*children=\[', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\]\s*\]', '', text)

    # Remove excessive parentheses from nested structures
    text = re.sub(r'\(+([\'"])', r'\1', text)
    text = re.sub(r'([\'"])\)+', r'\1', text)

    # Clean up quotes
    text = re.sub(r'\(\s*[\'"]([^\'"]+)[\'"]\s*\)', r'\1', text)
    text = text.replace("('", "'").replace("')", "'")

    # Fix spacing issues
    text = re.sub(r'\s+', ' ', text)  # Multiple spaces to single
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)  # Space before punctuation

    # Fix common OCR/parsing errors in the text
    text = text.replace('onfidential', 'Confidential')
    text = text.replace('c Confidential', 'Confidential')
    text = text.replace('I nformation', 'Information')
    text = text.replace('nformation', 'Information')
    text = text.replace('I equired', 'required')
    text = text.replace('ntellectual', 'Intellectual')
    text = text.replace(' o ', ' to ')
    text = text.replace('now such', 'know such')
    text = text.replace('k east', 'least')
    text = text.replace('l Confidential', 'Confidential')
    text = text.replace('i nformation', 'information')
    text = text.replace('ndependently', 'independently')
    text = text.replace('ubject', 'subject')
    text = text.replace(' s ', ' ')
    text = text.replace('he published', 'the published')

    # Remove leading/trailing quotes and whitespace
    text = text.strip('\'" \n\r\t')

    return text

def highlight_relevant_sentences(text, query, embedder, top_n=3):
    """
    Highlight the most relevant sentences in the text based on the query.
    Returns the text with HTML highlighting.
    """
    if not text or not query:
        return text

    # Split text into sentences (simple approach)
    sentences = re.split(r'(?<=[.!?])\s+', text)

    if len(sentences) <= 1:
        # If only one sentence, highlight the whole thing
        return f"**:green[{text}]**"

    # Embed query and sentences
    query_embedding = embedder.encode(query)
    sentence_embeddings = embedder.encode(sentences)

    # Calculate similarity scores
    similarities = []
    for sent_emb in sentence_embeddings:
        sim = np.dot(query_embedding, sent_emb) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(sent_emb)
        )
        similarities.append(sim)

    # Get indices of top N most similar sentences
    top_indices = np.argsort(similarities)[-top_n:][::-1]

    # Build highlighted text
    highlighted_sentences = []
    for i, sentence in enumerate(sentences):
        if i in top_indices:
            # Highlight this sentence
            highlighted_sentences.append(f"**:green[{sentence.strip()}]**")
        else:
            highlighted_sentences.append(sentence.strip())

    return " ".join(highlighted_sentences)

def display_result(result, index, query="", embedder=None):
    """Display a single search result"""
    score = result['score']
    raw_text = result['text']
    metadata = result['metadata']

    # Clean the text for better display
    text = clean_text(raw_text)

    # Create an expander for each result
    with st.expander(f"**Result {index + 1}** - Similarity: {score:.2%}", expanded=(index == 0)):
        # Display similarity score as a progress bar
        st.progress(score, text=f"Similarity Score: {score:.2%}")

        # Display metadata
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Source Document:**")
            file_name = os.path.basename(metadata.get('file_path', 'Unknown'))
            st.text(file_name)

            title = metadata.get('title', 'N/A')
            st.markdown(f"**Title:** {title}")

        with col2:
            author = metadata.get('author', 'N/A')
            st.markdown(f"**Author:** {author}")

            chunk_idx = metadata.get('chunk_index', 'N/A')
            st.markdown(f"**Chunk Index:** {chunk_idx}")

        st.divider()

        # Display the text content with highlighting
        st.markdown("**Text Content:**")

        # Highlight relevant sentences if query and embedder are provided
        if query and embedder:
            highlighted_text = highlight_relevant_sentences(text, query, embedder, top_n=3)
            st.markdown(highlighted_text)
            st.caption("🟢 Green text = most relevant to your query")
        else:
            # Format as paragraphs with blockquote styling for better readability
            paragraphs = text.split('\n')
            for para in paragraphs:
                if para.strip():
                    st.markdown(f"> {para.strip()}")

        # Provide copyable version with a toggle
        st.divider()
        if st.checkbox("Show copyable text", key=f"copy_{index}"):
            st.code(text, language=None)

        # Show additional metadata with a toggle instead of nested expander
        st.divider()
        if st.checkbox("Show Full Metadata", key=f"meta_{index}"):
            st.json(metadata)

def main():
    """Main application"""
    # Title and description
    st.title("🔍 Document Search Demo")
    st.markdown("""
    This demo showcases **semantic search** over your embedded documents.
    Enter a query below and the system will find the most relevant document chunks using AI-powered similarity matching.
    """)

    # Initialize MongoDB helper
    try:
        mongo_helper = get_mongo_helper()
    except Exception as e:
        st.error(f"Failed to connect to MongoDB: {str(e)}")
        st.stop()

    # Display sidebar
    display_sidebar(mongo_helper)

    # Example queries section
    st.subheader("💡 Example Queries")
    example_queries = [
        "What is machine learning?",
        "Tell me about neural networks",
        "How does data processing work?",
        "Resume experience and skills",
        "Research methodology and approach"
    ]

    cols = st.columns(len(example_queries))
    selected_example = None

    for idx, (col, query) in enumerate(zip(cols, example_queries)):
        with col:
            if st.button(query, key=f"example_{idx}", use_container_width=True):
                selected_example = query

    st.divider()

    # Search interface
    st.subheader("🔎 Search")

    # Query input
    default_query = selected_example if selected_example else ""
    query_text = st.text_input(
        "Enter your search query:",
        value=default_query,
        placeholder="e.g., machine learning algorithms",
        key="query_input"
    )

    # Settings in columns
    col1, col2 = st.columns(2)

    with col1:
        top_k = st.slider(
            "Number of results:",
            min_value=1,
            max_value=20,
            value=5,
            help="How many top results to return"
        )

    with col2:
        score_threshold = st.slider(
            "Similarity threshold:",
            min_value=0.0,
            max_value=1.0,
            value=0.0,
            step=0.05,
            help="Minimum similarity score (0.0 = show all results)"
        )

    # Search button
    search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)

    # Perform search
    if search_clicked and query_text:
        with st.spinner("Searching..."):
            try:
                # Get embedder for highlighting
                embedder = get_embedder()

                results = mongo_helper.search_similar(
                    query_text=query_text,
                    k=top_k,
                    score_threshold=score_threshold
                )

                st.divider()

                if results:
                    st.subheader(f"📄 Results ({len(results)} found)")

                    # Display each result with highlighting
                    for idx, result in enumerate(results):
                        display_result(result, idx, query=query_text, embedder=embedder)
                else:
                    st.warning("No results found. Try lowering the similarity threshold or using a different query.")

            except Exception as e:
                st.error(f"Search error: {str(e)}")
                st.exception(e)

    elif search_clicked and not query_text:
        st.warning("Please enter a search query.")

    # Footer
    st.divider()
    st.markdown("""
    <div style='text-align: center; color: #666; padding: 20px;'>
        <small>Powered by SentenceTransformers & MongoDB | Built with Streamlit</small>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
