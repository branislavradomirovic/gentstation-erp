import streamlit as st
import pandas as pd
import json
from core.database import get_session
from core.models import Integration, IntegrationEvent, Station
from ui.header import render_page_header
from core.activity_logger import log_activity
from core.integration_service import (
    get_integration_stats,
    list_import_batches,
    list_station_mappings,
    list_supported_integration_types,
    queue_csv_import_placeholder,
    upsert_integration,
    upsert_station_mapping,
)

def render(conn):
    render_page_header("🔌 External Integrations")
    st.markdown(
        '<div class="gs-page-intro">Connect your POS, pump controllers, or loyalty systems. Mapping external data to AI events allows for higher confidence in conversion and sales analytics.</div>',
        unsafe_allow_html=True,
    )

    with get_session() as session:
        stats = get_integration_stats(session, st.session_state.tenant_id)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Connected Systems", stats["active_integrations"])
        c2.metric("Total Events Imported", stats["total_events"])
        c3.metric("Station Mappings", stats["mapped_stations"])
        c4.metric("CSV Import Batches", stats["import_batches"])

        st.divider()

        tab_list, tab_add, tab_mappings, tab_history = st.tabs(
            ["Active Connections", "Add Integration", "Station Mapping", "Event Stream"]
        )

        with tab_list:
            integrations = session.query(Integration).all()
            if not integrations:
                st.info("No external systems connected yet.")
            else:
                df = pd.DataFrame([
                    {
                        "ID": i.id,
                        "Type": i.integration_type,
                        "Provider": i.provider,
                        "Display Name": i.display_name,
                        "Status": i.status,
                        "Secret Ref": i.secret_ref,
                    }
                    for i in integrations
                ])
                st.dataframe(df, use_container_width=True, hide_index=True)

        with tab_add:
            st.markdown("#### Register a new data source")
            with st.form("add_integration_form"):
                i_type = st.selectbox("System Type", list_supported_integration_types())
                i_provider = st.text_input("Provider Name", placeholder="e.g. Gilbarco, Petrotec")
                i_display_name = st.text_input("Display Name", placeholder="Friendly name shown in the workspace")
                i_config = st.text_area("Configuration (JSON)", value='{}')
                i_metadata = st.text_area("Metadata (JSON)", value='{}', help="Non-secret provider metadata, capabilities, notes, or import hints.")
                i_secret = st.text_input("Secret Reference", help="Reference to an environment variable or secret manager key.")
                i_secret_refs = st.text_area("Secret References (JSON)", value='{}', help="Optional named secret references, e.g. {\"api_key\": \"env://POS_API_KEY\"}")

                if st.form_submit_button("Save Integration"):
                    try:
                        config = json.loads(i_config)
                        metadata = json.loads(i_metadata)
                        secret_refs = json.loads(i_secret_refs)
                        integration = upsert_integration(
                            session,
                            tenant_id=st.session_state.tenant_id,
                            integration_type=i_type,
                            provider=i_provider,
                            display_name=i_display_name,
                            config_json=config,
                            metadata_json=metadata,
                            secret_ref=i_secret,
                            secret_refs_json=secret_refs,
                        )
                        session.commit()
                        log_activity(conn, "CREATE_INTEGRATION", f"Saved {i_type} integration from {integration.provider}")
                        st.success("Integration registered.")
                        st.rerun()
                    except json.JSONDecodeError:
                        st.error("Invalid JSON configuration.")
                    except Exception as e:
                        st.error(f"Error: {e}")

        with tab_mappings:
            st.markdown("#### Map stations to external system IDs")
            integrations = session.query(Integration).order_by(Integration.provider).all()
            stations = session.query(Station).order_by(Station.name).all()

            if not integrations or not stations:
                st.info("Create at least one integration and one station before adding mappings.")
            else:
                integration_options = {f"{i.provider} ({i.integration_type})": i for i in integrations}
                station_options = {s.name: s for s in stations}
                with st.form("integration_station_mapping_form"):
                    selected_integration_label = st.selectbox("Integration", list(integration_options.keys()))
                    selected_station_name = st.selectbox("Station", list(station_options.keys()))
                    external_station_id = st.text_input("External Station ID")
                    external_location_id = st.text_input("External Location ID (optional)")
                    mapping_metadata = st.text_area("Mapping Metadata (JSON)", value='{}')

                    if st.form_submit_button("Save Mapping"):
                        try:
                            mapping = upsert_station_mapping(
                                session,
                                tenant_id=st.session_state.tenant_id,
                                integration_id=integration_options[selected_integration_label].id,
                                station_id=station_options[selected_station_name].id,
                                external_station_id=external_station_id,
                                external_location_id=external_location_id,
                                metadata_json=json.loads(mapping_metadata),
                            )
                            session.commit()
                            log_activity(
                                conn,
                                "UPSERT_INTEGRATION_MAPPING",
                                f"Mapped station {mapping.station_id} to external station {mapping.external_station_id}",
                            )
                            st.success("Station mapping saved.")
                            st.rerun()
                        except json.JSONDecodeError:
                            st.error("Invalid mapping metadata JSON.")
                        except Exception as e:
                            st.error(f"Error: {e}")

                mappings = list_station_mappings(session, st.session_state.tenant_id)
                if mappings:
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Integration ID": row.integration_id,
                                    "Station ID": row.station_id,
                                    "External Station ID": row.external_station_id,
                                    "External Location ID": row.external_location_id,
                                }
                                for row in mappings
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

        with tab_history:
            st.markdown("#### Recent Integration Events")
            events_query = session.query(IntegrationEvent).order_by(IntegrationEvent.occurred_at.desc()).limit(50)
            events_list = []
            for e in events_query:
                events_list.append({
                    "Time": e.occurred_at,
                    "Type": e.event_type,
                    "Ext ID": e.external_id,
                    "Payload": str(e.payload_json)[:100] + "..."
                })

            if not events_list:
                st.info("Waiting for external data stream...")
            else:
                st.dataframe(pd.DataFrame(events_list), use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("#### Manual CSV Import (Placeholder)")
            uploaded_file = st.file_uploader("Upload sales or pump events CSV", type="csv")
            if uploaded_file:
                integrations = session.query(Integration).order_by(Integration.provider).all()
                if not integrations:
                    st.info("Create an integration before queueing a CSV placeholder import.")
                else:
                    import_target = st.selectbox(
                        "Import Target",
                        options=integrations,
                        format_func=lambda item: f"{item.provider} ({item.integration_type})",
                        key="csv_import_target",
                    )
                    if st.button("Queue CSV Placeholder Import"):
                        file_bytes = uploaded_file.getvalue()
                        batch = queue_csv_import_placeholder(
                            session,
                            tenant_id=st.session_state.tenant_id,
                            integration_id=import_target.id,
                            filename=uploaded_file.name,
                            content_bytes=file_bytes,
                            metadata_json={"integration_type": import_target.integration_type},
                        )
                        session.commit()
                        log_activity(
                            conn,
                            "QUEUE_INTEGRATION_IMPORT",
                            f"Queued CSV placeholder import {batch.id} for integration {import_target.id}",
                        )
                        st.success("CSV placeholder import queued in Postgres for future mapping.")
                        st.json(batch.metadata_json or {})

            import_batches = list_import_batches(session, st.session_state.tenant_id)
            if import_batches:
                st.markdown("#### Import Queue")
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Batch ID": batch.id,
                                "Integration ID": batch.integration_id,
                                "Type": batch.import_type,
                                "Status": batch.status,
                                "Filename": batch.source_filename,
                                "Created": batch.created_at,
                            }
                            for batch in import_batches
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
