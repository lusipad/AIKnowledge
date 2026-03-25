from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConfigProfile, ConfigProfileVersion
from app.services.resource_acl import default_config_acl
from app.utils import generate_id


DEFAULT_PROFILES = [
    {
        "scope_type": "repo",
        "scope_id": "demo-repo",
        "profile_type": "prompt",
        "content": {
            "instructions": [
                "优先复用现有模块和规则引擎。",
                "新增逻辑前先检查当前目录是否已有相似实现。",
                "所有业务规则变更都需要补充回归检查项。",
            ]
        },
        "version": 1,
        "status": "active",
    },
    {
        "scope_type": "path",
        "scope_id": "src/order/risk",
        "profile_type": "prompt",
        "content": {
            "instructions": [
                "风控规则必须通过统一规则引擎接入。",
                "禁止在 controller 直接拼装风控条件。",
            ]
        },
        "version": 1,
        "status": "active",
    },
]


def seed_default_profiles(database: Session) -> None:
    existing_profile = database.scalar(select(ConfigProfile.profile_id).limit(1))
    if existing_profile:
        return

    for profile in DEFAULT_PROFILES:
        profile_id = generate_id("cfg")
        database.add(
            ConfigProfile(
                profile_id=profile_id,
                tenant_id=None,
                team_id=None,
                scope_type=profile["scope_type"],
                scope_id=profile["scope_id"],
                profile_type=profile["profile_type"],
                content=profile["content"],
                acl=default_config_acl(None),
                version=profile["version"],
                status=profile["status"],
            )
        )
        database.add(
            ConfigProfileVersion(
                profile_id=profile_id,
                tenant_id=None,
                team_id=None,
                version=profile["version"],
                content=profile["content"],
                acl=default_config_acl(None),
                status=profile["status"],
            )
        )

    database.commit()
