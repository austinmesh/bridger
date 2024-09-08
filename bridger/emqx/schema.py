from dataclasses import dataclass, field
from typing import Literal, Optional, Union


@dataclass
class AuthnHashSimple:
    name: str  # Simple password hashing algorithm
    salt_position: str = "prefix"  # Salt position for the algorithm

    def __post_init__(self):
        # Validate enums for `name` and `salt_position`
        valid_algorithms = ["plain", "md5", "sha", "sha256", "sha512"]
        valid_salt_positions = ["disable", "prefix", "suffix"]

        if self.name not in valid_algorithms:
            raise ValueError(f"Invalid hashing algorithm: {self.name}")

        if self.salt_position not in valid_salt_positions:
            raise ValueError(f"Invalid salt position: {self.salt_position}")


@dataclass
class AuthnHashBcryptRW:
    name: str = "bcrypt"  # BCRYPT password hashing
    salt_rounds: int = 10  # Work factor for BCRYPT

    def __post_init__(self):
        if self.name != "bcrypt":
            raise ValueError(f"Invalid hashing algorithm: {self.name}")
        if not (5 <= self.salt_rounds <= 10):
            raise ValueError("salt_rounds must be between 5 and 10")


@dataclass
class AuthnHashPBKDF2:
    name: str = "pbkdf2"  # PBKDF2 password hashing
    mac_fun: str = "sha256"  # Mac function for PBKDF2
    iterations: int = 1000  # Iteration count for PBKDF2
    dk_length: Optional[int] = None  # Derived length for PBKDF2 hashing algorithm

    def __post_init__(self):
        valid_mac_funs = ["md4", "md5", "ripemd160", "sha", "sha224", "sha256", "sha384", "sha512"]

        if self.name != "pbkdf2":
            raise ValueError(f"Invalid hashing algorithm: {self.name}")

        if self.mac_fun not in valid_mac_funs:
            raise ValueError(f"Invalid mac function: {self.mac_fun}")

        if self.iterations < 1:
            raise ValueError("iterations must be at least 1")

        if self.dk_length is not None and self.dk_length < 1:
            raise ValueError("dk_length must be at least 1 if specified")


@dataclass
class Authn:
    id: str
    mechanism: str


@dataclass
class AuthnBuiltinDB(Authn):
    backend: str
    user_id_type: str = "username"
    bootstrap_file: str = "${EMQX_ETC_DIR}/auth-built-in-db-bootstrap.csv"
    bootstrap_type: str = "plain"
    enable: bool = True

    password_hash_algorithm: Optional[Union[AuthnHashSimple, AuthnHashBcryptRW, AuthnHashPBKDF2]] = field(
        default_factory=dict
    )

    def __post_init__(self):
        valid_mechanisms = ["password_based"]
        valid_backends = ["built_in_database"]
        valid_user_id_types = ["username", "clientid"]

        if self.mechanism not in valid_mechanisms:
            raise ValueError(f"Invalid mechanism: {self.mechanism}")

        if self.backend not in valid_backends:
            raise ValueError(f"Invalid backend: {self.backend}")

        if self.user_id_type not in valid_user_id_types:
            raise ValueError(f"Invalid user_id_type: {self.user_id_type}")


@dataclass
class AuthorizationRule:
    topic: str
    permission: Literal["allow", "deny"] = "allow"
    action: Literal["all", "publish", "subscribe"] = "all"
    retain: Union[bool, Literal["all"]] = False
    qos: list[Literal[0, 1, 2]] = field(default_factory=list)

    def __post_init__(self):
        valid_permissions = ["allow", "deny"]
        valid_actions = ["all", "publish", "subscribe"]

        if self.permission not in valid_permissions:
            raise ValueError(f"Invalid permission: {self.permission}")

        if self.action not in valid_actions:
            raise ValueError(f"Invalid action: {self.action}")


@dataclass
class AuthorizationUsersRules:
    username: str
    rules: list[AuthorizationRule]

    def __post_init__(self):
        self.rules = [AuthorizationRule(**rule) for rule in self.rules]


@dataclass
class EMQXError:
    code: str
    message: str


@dataclass
class User:
    user_id: str
    password: Optional[str] = None
    is_superuser: Optional[bool] = None


@dataclass
class PublicMeta:
    hasnext: bool
    limit: Optional[int] = None
    count: Optional[int] = None
    page: Optional[int] = None


@dataclass
class ResponseUsers:
    users: list[User]
    meta: PublicMeta

    def __post_init__(self):
        self.users = [User(**user) for user in self.users]
        self.meta = PublicMeta(**self.meta)
