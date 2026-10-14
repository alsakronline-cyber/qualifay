from app.services.site_contacts import pick_emails


def test_only_the_sites_own_domain():
    text = "mail info@acme.com or partner@gmail.com, ceo@other.io"
    assert pick_emails(text, "https://www.acme.com/") == ["info@acme.com"]


def test_role_inboxes_first_and_deduped():
    text = "john.doe@acme.com  hello@acme.com  HELLO@acme.com"
    assert pick_emails(text, "acme.com") == ["hello@acme.com", "john.doe@acme.com"]


def test_junk_and_placeholders_dropped():
    text = "logo@2x.png you@example.com info@acme.com"
    assert pick_emails(text, "https://acme.com") == ["info@acme.com"]


def test_subdomains_match():
    assert pick_emails("sales@mail.acme.co.uk", "https://acme.co.uk") == ["sales@mail.acme.co.uk"]


def test_nothing_found():
    assert pick_emails("no contacts here", "https://acme.com") == []
