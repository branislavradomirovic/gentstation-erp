def render(conn):
    import streamlit as st

    st.warning("This page has been consolidated into the main Home Dashboard.")
    if st.button("Go to Home Dashboard"):
        st.session_state.active_page = "Dashboard"
        st.rerun()
