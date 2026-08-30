"""
Streamlit chat interface (Step 5 of the build).

Minimal single-page chat UI using st.chat_message and st.chat_input.
No theming, no extra pages — time is better spent on data correctness.
"""

import streamlit as st
from agent import handle_message
from config import get_config
from monday_client import get_board_name

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Monday.com BI Agent",
    page_icon="📊",
    layout="centered",
)

# ---------------------------------------------------------------------------
# Sidebar — connected boards info
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📊 BI Agent")
    st.caption("Executive Insights Dashboard")

    st.divider()
    st.subheader("Connected Boards")

    config = get_config()

    # Validate configuration
    missing_config = []
    if not config.get("MONDAY_API_TOKEN"):
        missing_config.append("MONDAY_API_TOKEN")
    if not config.get("GEMINI_API_KEY"):
        missing_config.append("GEMINI_API_KEY")
    if not config.get("WORK_ORDERS_BOARD_ID"):
        missing_config.append("WORK_ORDERS_BOARD_ID")
    if not config.get("DEALS_BOARD_ID"):
        missing_config.append("DEALS_BOARD_ID")

    if missing_config:
        st.error(f"Missing configuration: {', '.join(missing_config)}")
        st.info("Set these in `.streamlit/secrets.toml` or as environment variables.")
    else:
        # Show connected board names
        try:
            wo_name = get_board_name(config["WORK_ORDERS_BOARD_ID"], config["MONDAY_API_TOKEN"])
            deals_name = get_board_name(config["DEALS_BOARD_ID"], config["MONDAY_API_TOKEN"])
            st.success("✅ Connected to Monday.com")
            st.markdown(f"**Work Orders:** {wo_name}")
            st.markdown(f"**Deals:** {deals_name}")
        except Exception as e:
            st.error(f"Connection error: {str(e)}")

    st.divider()
    st.caption("💡 **Example questions:**")
    st.markdown("""
- How's our pipeline for Mining?
- Which deals are stuck in proposals?
- Give me a leadership update
- Any overdue work orders?
- Total pipeline value by sector?
    """)

    st.divider()
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conversation_history = []
        st.rerun()

    st.caption("Data is queried in real-time directly from Monday.com.")


# ---------------------------------------------------------------------------
# Chat interface
# ---------------------------------------------------------------------------

st.title("Executive Intelligence Agent")
st.caption("Ask natural language questions to analyze your live Deals and Work Orders data.")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = []

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Ask a business question..."):
    # Check configuration before processing
    if missing_config:
        st.error(
            "Cannot process queries — missing configuration. "
            "Please set all required secrets (see sidebar)."
        )
    else:
        # Display user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get agent response
        with st.chat_message("assistant"):
            with st.spinner("Querying Monday.com and analyzing data..."):
                try:
                    response_text, updated_history = handle_message(
                        prompt,
                        st.session_state.conversation_history,
                    )
                    st.markdown(response_text)
                    st.session_state.conversation_history = updated_history
                    st.session_state.messages.append(
                        {"role": "assistant", "content": response_text}
                    )
                except Exception as e:
                    error_msg = f"An error occurred: {str(e)}"
                    st.error(error_msg)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": error_msg}
                    )
