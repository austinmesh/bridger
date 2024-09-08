import pytest

from bridger.emqx.schema import (
    AuthnBuiltinDB,
    AuthnHashBcryptRW,
    AuthnHashPBKDF2,
    AuthnHashSimple,
    AuthorizationRule,
    AuthorizationUsersRules,
    PublicMeta,
    ResponseUsers,
    User,
)


# Testing AuthnHashSimple
def test_authn_hash_simple_valid():
    hash_simple = AuthnHashSimple(name="sha256", salt_position="suffix")
    assert hash_simple.name == "sha256"
    assert hash_simple.salt_position == "suffix"


def test_authn_hash_simple_invalid_algorithm():
    with pytest.raises(ValueError):
        AuthnHashSimple(name="invalid")


def test_authn_hash_simple_invalid_salt_position():
    with pytest.raises(ValueError):
        AuthnHashSimple(name="sha256", salt_position="invalid")


# Testing AuthnHashBcryptRW
def test_authn_hash_bcrypt_valid():
    hash_bcrypt = AuthnHashBcryptRW(salt_rounds=8)
    assert hash_bcrypt.name == "bcrypt"
    assert hash_bcrypt.salt_rounds == 8


def test_authn_hash_bcrypt_invalid_rounds():
    with pytest.raises(ValueError):
        AuthnHashBcryptRW(salt_rounds=4)


# Testing AuthnHashPBKDF2
def test_authn_hash_pbkdf2_valid():
    hash_pbkdf2 = AuthnHashPBKDF2(mac_fun="sha512", iterations=2000)
    assert hash_pbkdf2.name == "pbkdf2"
    assert hash_pbkdf2.mac_fun == "sha512"
    assert hash_pbkdf2.iterations == 2000


def test_authn_hash_pbkdf2_invalid_mac_fun():
    with pytest.raises(ValueError):
        AuthnHashPBKDF2(mac_fun="invalid")


def test_authn_hash_pbkdf2_invalid_iterations():
    with pytest.raises(ValueError):
        AuthnHashPBKDF2(iterations=0)


# Testing AuthnBuiltinDB
def test_authn_builtindb_valid():
    authn_builtin = AuthnBuiltinDB(id="1", mechanism="password_based", backend="built_in_database")
    assert authn_builtin.id == "1"
    assert authn_builtin.mechanism == "password_based"
    assert authn_builtin.backend == "built_in_database"


def test_authn_builtindb_invalid_mechanism():
    with pytest.raises(ValueError):
        AuthnBuiltinDB(id="1", mechanism="invalid", backend="built_in_database")


def test_authn_builtindb_invalid_backend():
    with pytest.raises(ValueError):
        AuthnBuiltinDB(id="1", mechanism="password_based", backend="invalid")


# Testing AuthorizationRule
def test_authorization_rule_valid():
    rule = AuthorizationRule(topic="my/topic", permission="allow", action="publish", qos=[0, 1])
    assert rule.topic == "my/topic"
    assert rule.permission == "allow"
    assert rule.action == "publish"
    assert rule.qos == [0, 1]


def test_authorization_rule_invalid_permission():
    with pytest.raises(ValueError):
        AuthorizationRule(topic="my/topic", permission="invalid")


# Testing AuthorizationUsersRules
def test_authorization_users_rules():
    rules = [{"topic": "my/topic", "permission": "allow", "action": "publish", "qos": [0]}]
    auth_user_rules = AuthorizationUsersRules(username="user1", rules=rules)
    assert auth_user_rules.username == "user1"
    assert len(auth_user_rules.rules) == 1
    assert auth_user_rules.rules[0].topic == "my/topic"


# Testing User
def test_user():
    user = User(user_id="user1", password="secret", is_superuser=True)
    assert user.user_id == "user1"
    assert user.password == "secret"
    assert user.is_superuser is True


# Testing PublicMeta
def test_public_meta():
    meta = PublicMeta(hasnext=True, limit=100, count=10, page=1)
    assert meta.hasnext is True
    assert meta.limit == 100
    assert meta.count == 10
    assert meta.page == 1


# Testing ResponseUsers
def test_response_users():
    users = [{"user_id": "user1"}, {"user_id": "user2"}]
    meta = {"hasnext": True, "limit": 100, "count": 10, "page": 1}
    response_users = ResponseUsers(users=users, meta=meta)

    assert len(response_users.users) == 2
    assert response_users.users[0].user_id == "user1"
    assert response_users.meta.limit == 100
