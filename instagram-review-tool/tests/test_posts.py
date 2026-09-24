import pytest

from instagram.exceptions import (
    InstagramAuthError,
    InstagramPostNotPublicError,
    InstagramRateLimitError,
)
from services.comment_service import add_comment, get_comment_count, get_comments
from services.errors import EmptyCommentError, InvalidInstagramURLError, PostNotFoundError
from services.post_service import create_post, get_post, list_posts
from services.vote_service import add_upvote, get_upvote_count
from tests.conftest import FakeInstagramClient

URL = "https://www.instagram.com/p/C0ffee123/"


# ---------------------------------------------------------------- posts


def test_create_post_saves_post(db, fake_client):
    result = create_post(URL, client=fake_client)

    assert result.created is True
    assert result.post.id is not None
    assert result.post.instagram_url == URL
    assert result.post.embed_html
    assert get_post(result.post.id).instagram_url == URL
    assert fake_client.calls == [URL]


def test_create_post_trims_and_normalizes_url(db, fake_client):
    result = create_post("  https://instagram.com/p/C0ffee123?igsh=abc  ", client=fake_client)
    assert result.post.instagram_url == URL


def test_duplicate_post_is_not_created(db, fake_client):
    first = create_post(URL, client=fake_client)
    second = create_post(URL, client=fake_client)

    assert second.created is False
    assert second.post.id == first.post.id
    assert len(list_posts()) == 1
    assert fake_client.calls == [URL]  # Instagram not called again for a known URL


def test_duplicate_detected_across_url_variants(db, fake_client):
    create_post(URL, client=fake_client)
    second = create_post("https://m.instagram.com/someuser/p/C0ffee123", client=fake_client)
    assert second.created is False
    assert len(list_posts()) == 1


def test_invalid_url_is_rejected_without_calling_instagram(db, fake_client):
    with pytest.raises(InvalidInstagramURLError):
        create_post("https://example.com/p/C0ffee123/", client=fake_client)
    assert fake_client.calls == []
    assert list_posts() == []


@pytest.mark.parametrize(
    "error",
    [InstagramAuthError(), InstagramRateLimitError(), InstagramPostNotPublicError()],
)
def test_instagram_failure_does_not_save_post(db, error):
    with pytest.raises(type(error)):
        create_post(URL, client=FakeInstagramClient(error=error))
    assert list_posts() == []


def test_list_posts_newest_first(db, fake_client):
    a = create_post("https://www.instagram.com/p/AAAAA/", client=fake_client).post
    b = create_post("https://www.instagram.com/p/BBBBB/", client=fake_client).post
    assert [p.id for p in list_posts()] == [b.id, a.id]


# ---------------------------------------------------------------- upvotes


def test_add_upvote(db, fake_client):
    post = create_post(URL, client=fake_client).post
    assert add_upvote(post.id) == 1


def test_count_upvotes(db, fake_client):
    post = create_post(URL, client=fake_client).post
    other = create_post("https://www.instagram.com/p/OTHER1/", client=fake_client).post
    assert get_upvote_count(post.id) == 0

    for _ in range(3):
        add_upvote(post.id)
    add_upvote(other.id)

    assert get_upvote_count(post.id) == 3
    assert get_upvote_count(other.id) == 1


def test_upvote_unknown_post(db):
    with pytest.raises(PostNotFoundError):
        add_upvote(999)


# ---------------------------------------------------------------- comments


def test_add_comment_trims_text(db, fake_client):
    post = create_post(URL, client=fake_client).post
    comment = add_comment(post.id, "  This item is available in warehouse A.  ")
    assert comment.comment_text == "This item is available in warehouse A."
    assert comment.post_id == post.id


@pytest.mark.parametrize("text", ["", "   ", "\n\t", None])
def test_empty_comment_rejected(db, fake_client, text):
    post = create_post(URL, client=fake_client).post
    with pytest.raises(EmptyCommentError):
        add_comment(post.id, text)
    assert get_comments(post.id) == []


def test_get_comments_in_order(db, fake_client):
    post = create_post(URL, client=fake_client).post
    other = create_post("https://www.instagram.com/p/OTHER1/", client=fake_client).post
    add_comment(post.id, "first")
    add_comment(other.id, "elsewhere")
    add_comment(post.id, "second")

    assert [c.comment_text for c in get_comments(post.id)] == ["first", "second"]
    assert get_comment_count(post.id) == 2


def test_comment_unknown_post(db):
    with pytest.raises(PostNotFoundError):
        add_comment(999, "hello")


def test_data_survives_restart(tmp_path, fake_client):
    from database.db import init_db

    url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(url)
    post = create_post(URL, client=fake_client).post
    add_upvote(post.id)
    add_comment(post.id, "persisted")

    init_db(url)  # new engine, same file — like restarting Streamlit
    assert [p.id for p in list_posts()] == [post.id]
    assert get_upvote_count(post.id) == 1
    assert [c.comment_text for c in get_comments(post.id)] == ["persisted"]
