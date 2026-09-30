from autonomous_remediation.offline_ticket_augmentation import (
    SiteContextEvidence,
    SiteContextState,
    SiteWitness,
    classify_site_context,
    is_offline_ticket,
    render_site_context_note,
)


def witness(
    name,
    *,
    online,
    role="server",
    fixed=True,
    mobile=False,
    confirmed=True,
    live=False,
):
    return SiteWitness(
        device_uid=f"uid-{name}",
        hostname=name,
        role=role,
        online=online,
        fixed=fixed,
        mobile=mobile,
        site_presence_confirmed=confirmed,
        live_read_succeeded=live,
    )


def test_offline_trigger_requires_bounded_language_or_device_context():
    assert is_offline_ticket(title="Server is offline")
    assert is_offline_ticket(
        title="RIG-PC-01 Offline",
        has_device_context=True,
    )
    assert not is_offline_ticket(title="User requested offline files")


def test_live_on_site_server_confirms_site_up():
    result = classify_site_context(
        SiteContextEvidence(
            target_hostname="PC-1",
            target_drmm_online=False,
            target_deb_online=False,
            site_name="Riggins",
            witnesses=(
                witness("RIG-SRV", online=True, live=True),
            ),
        )
    )
    assert result.state is SiteContextState.CONFIRMED_UP


def test_live_server_plus_multiple_offline_fixed_peers_is_partial_outage():
    result = classify_site_context(
        SiteContextEvidence(
            target_hostname="PC-1",
            target_drmm_online=False,
            target_deb_online=False,
            site_name="Riggins",
            witnesses=(
                witness("RIG-SRV", online=True, live=True),
                witness("RIG-PC-2", online=False, role="desktop"),
                witness("RIG-PC-3", online=False, role="desktop"),
            ),
        )
    )
    assert result.state is SiteContextState.PARTIAL_OR_SEGMENT


def test_two_online_fixed_peers_make_site_likely_up_without_active_probe():
    result = classify_site_context(
        SiteContextEvidence(
            target_hostname="PC-1",
            target_drmm_online=False,
            target_deb_online=None,
            site_name="Riggins",
            witnesses=(
                witness("RIG-PC-2", online=True, role="desktop"),
                witness("RIG-PC-3", online=True, role="desktop"),
            ),
        )
    )
    assert result.state is SiteContextState.LIKELY_UP


def test_multiple_offline_fixed_peers_make_site_likely_down():
    result = classify_site_context(
        SiteContextEvidence(
            target_hostname="PC-1",
            target_drmm_online=False,
            target_deb_online=False,
            site_name="Riggins",
            witnesses=(
                witness("RIG-SRV", online=False),
                witness("RIG-PC-2", online=False, role="desktop"),
            ),
        )
    )
    assert result.state is SiteContextState.LIKELY_DOWN


def test_online_mobile_devices_do_not_prove_site_health():
    result = classify_site_context(
        SiteContextEvidence(
            target_hostname="PC-1",
            target_drmm_online=False,
            target_deb_online=False,
            site_name="Riggins",
            witnesses=(
                witness(
                    "LAPTOP-1",
                    online=True,
                    role="laptop",
                    fixed=False,
                    mobile=True,
                    confirmed=False,
                ),
            ),
        )
    )
    assert result.state is SiteContextState.UNKNOWN
    assert result.excluded_mobile_online == ("LAPTOP-1",)


def test_deb_online_does_not_prove_site_but_flags_rmm_conflict():
    result = classify_site_context(
        SiteContextEvidence(
            target_hostname="PC-1",
            target_drmm_online=False,
            target_deb_online=True,
            site_name=None,
        )
    )
    assert result.state is SiteContextState.UNKNOWN
    assert result.target_online_outside_drmm is True


def test_note_is_short_and_explicitly_non_owning():
    result = classify_site_context(
        SiteContextEvidence(
            target_hostname="PC-1",
            target_drmm_online=False,
            target_deb_online=False,
            site_name="Riggins",
            witnesses=(witness("RIG-SRV", online=True, live=True),),
        )
    )
    note = render_site_context_note(
        result,
        target_drmm_online=False,
        target_deb_online=False,
        site_name="Riggins",
    )
    assert "STATUS: Site confirmed up." in note
    assert "has not taken ownership" in note
    assert "CHANGES MADE: None." in note
