# 阿里云证书服务集成方案

> **文档性质**: 二期规划提案
> **创建日期**: 2026-04-09
> **目标里程碑**: Phase 4 / M5

---

## 1. 概述

本文档描述将阿里云 SSL 证书服务集成到 Cert Control Plane 的技术方案。集成后，控制平面可自动从阿里云拉取证书、监控到期时间、并在到期前自动续期。

### 1.1 当前架构

```
外部证书源 ──手动上传──> 控制平面 ──分发──> Agent 节点
     │
     └─ 阿里云控制台导出证书/私钥，手动上传到控制平面
```

### 1.2 目标架构

```
阿里云 SSL 证书服务
        │
        ▼ API 自动拉取
┌───────────────────┐
│    控制平面        │
│  ┌─────────────┐  │
│  │ Provider    │  │
│  │ Adapter     │──┼── 自动同步证书
│  │ (Aliyun)    │  │
│  └─────────────┘  │
│        │          │
│        ▼          │
│  ExternalCert     │
│  (自动更新)        │
└───────────────────┘
        │
        ▼ 分发
    Agent 节点
```

---

## 2. 阿里云 SSL 证书 API 概览

### 2.1 核心接口

| 接口 | 用途 | 文档 |
|------|------|------|
| `DescribeUserCertificateList` | 获取证书列表 | [链接](https://help.aliyun.com/document_detail/138875.html) |
| `DescribeUserCertificateDetail` | 获取证书详情 | [链接](https://help.aliyun.com/document_detail/138876.html) |
| `DownloadCertificate` | 下载证书内容 | [链接](https://help.aliyun.com/document_detail/138877.html) |
| `CreateCertificateRequest` | 申请证书 | [链接](https://help.aliyun.com/document_detail/138878.html) |
| `RenewCertificate` | 续期证书 | [链接](https://help.aliyun.com/document_detail/138879.html) |

### 2.2 认证方式

阿里云 API 使用 **AccessKey** 认证：
- `AccessKey ID`: 标识用户身份
- `AccessKey Secret`: 签名密钥

建议使用 **RAM 子账号**，仅授予 `AliyunCASReadOnlyAccess` 权限。

### 2.3 SDK

```bash
pip install aliyun-python-sdk-cas
```

或使用 HTTP API + 签名算法。

---

## 3. 数据模型扩展

### 3.1 新增 Provider 模型

```python
# server/app/models.py

class CertificateProvider(Base):
    """证书提供商配置"""
    __tablename__ = "certificate_providers"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)  # aliyun, letsencrypt, internal-pki
    provider_type = Column(String(30), nullable=False)  # aliyun-cas, acme, internal

    # 加密存储的凭据配置 (JSON)
    credentials_encrypted = Column(Text, nullable=True)

    # 同步配置
    sync_enabled = Column(Boolean, default=True)
    sync_interval = Column(Integer, default=3600)  # 秒
    last_sync_at = Column(DateTime, nullable=True)

    # 自动续期配置
    auto_renew_enabled = Column(Boolean, default=False)
    renew_before_days = Column(Integer, default=30)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    # 关联
    external_certs = relationship("ExternalCertificate", back_populates="provider_obj")
```

### 3.2 扩展 ExternalCertificate

```python
# 现有字段已有: provider, external_id
# 新增字段:

class ExternalCertificate(Base):
    # ... 现有字段 ...

    # Provider 关联
    provider_id = Column(Integer, ForeignKey("certificate_providers.id"), nullable=True)
    provider_obj = relationship("CertificateProvider", back_populates="external_certs")

    # 同步状态
    sync_status = Column(String(20), default="manual")  # manual, synced, sync_failed
    last_sync_at = Column(DateTime, nullable=True)
    sync_error = Column(Text, nullable=True)

    # 续期状态
    renewal_status = Column(String(20), nullable=True)  # pending, in_progress, completed, failed
    renewal_task_id = Column(String(100), nullable=True)
```

### 3.3 数据库迁移

```python
# server/alembic/versions/xxx_add_provider_support.py

def upgrade():
    # 创建 providers 表
    op.create_table(
        'certificate_providers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(50), unique=True, nullable=False),
        sa.Column('provider_type', sa.String(30), nullable=False),
        sa.Column('credentials_encrypted', sa.Text(), nullable=True),
        sa.Column('sync_enabled', sa.Boolean(), default=True),
        sa.Column('sync_interval', sa.Integer(), default=3600),
        sa.Column('last_sync_at', sa.DateTime(), nullable=True),
        sa.Column('auto_renew_enabled', sa.Boolean(), default=False),
        sa.Column('renew_before_days', sa.Integer(), default=30),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), onupdate=datetime.utcnow),
    )

    # 扩展 external_certificates 表
    op.add_column('external_certificates',
        sa.Column('provider_id', sa.Integer(), sa.ForeignKey('certificate_providers.id'), nullable=True))
    op.add_column('external_certificates', sa.Column('sync_status', sa.String(20), default='manual'))
    op.add_column('external_certificates', sa.Column('last_sync_at', sa.DateTime(), nullable=True))
    op.add_column('external_certificates', sa.Column('sync_error', sa.Text(), nullable=True))
    op.add_column('external_certificates', sa.Column('renewal_status', sa.String(20), nullable=True))
    op.add_column('external_certificates', sa.Column('renewal_task_id', sa.String(100), nullable=True))
```

---

## 4. Provider 抽象层设计

### 4.1 基类接口

```python
# server/app/providers/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

@dataclass
class ProviderCertificate:
    """Provider 返回的证书数据"""
    external_id: str
    subject_cn: str
    serial_hex: str
    not_before: datetime
    not_after: datetime
    cert_pem: Optional[str] = None
    key_pem: Optional[str] = None
    status: str = "issued"  # issued, expired, revoked, pending


class CertificateProviderBase(ABC):
    """证书提供商抽象基类"""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def list_certificates(self) -> List[ProviderCertificate]:
        """获取证书列表"""
        pass

    @abstractmethod
    async def get_certificate(self, external_id: str) -> ProviderCertificate:
        """获取证书详情"""
        pass

    @abstractmethod
    async def download_certificate(self, external_id: str) -> ProviderCertificate:
        """下载证书内容 (含私钥)"""
        pass

    @abstractmethod
    async def renew_certificate(self, external_id: str) -> str:
        """续期证书，返回续期任务 ID"""
        pass

    @abstractmethod
    def validate_credentials(self) -> bool:
        """验证凭据是否有效"""
        pass
```

### 4.2 阿里云实现

```python
# server/app/providers/aliyun.py

import json
import base64
from datetime import datetime
from typing import List, Optional

from aliyunsdkcore.client import AcsClient
from aliyunsdkcas.request.v20200407 import (
    DescribeUserCertificateListRequest,
    DescribeUserCertificateDetailRequest,
    DownloadCertificateRequest,
)

from .base import CertificateProviderBase, ProviderCertificate
from app.core.crypto import encrypt_value, decrypt_value


class AliyunCASProvider(CertificateProviderBase):
    """阿里云 SSL 证书服务 Provider"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._client: Optional[AcsClient] = None

    @property
    def client(self) -> AcsClient:
        if self._client is None:
            self._client = AcsClient(
                self.config['access_key_id'],
                self.config['access_key_secret'],
                self.config.get('region', 'cn-hangzhou')
            )
        return self._client

    async def list_certificates(self) -> List[ProviderCertificate]:
        """获取证书列表"""
        request = DescribeUserCertificateListRequest.DescribeUserCertificateListRequest()
        request.set_ShowSize(100)
        request.set_CurrentPage(1)

        response = self.client.do_action_with_exception(request)
        data = json.loads(response)

        certs = []
        for item in data.get('Certificates', []):
            cert = ProviderCertificate(
                external_id=str(item['CertId']),
                subject_cn=item.get('CommonName', ''),
                serial_hex=item.get('SerialNo', ''),
                not_before=self._parse_date(item.get('StartDate')),
                not_after=self._parse_date(item.get('EndDate')),
                status=self._map_status(item.get('Status'))
            )
            certs.append(cert)

        return certs

    async def get_certificate(self, external_id: str) -> ProviderCertificate:
        """获取证书详情"""
        request = DescribeUserCertificateDetailRequest.DescribeUserCertificateDetailRequest()
        request.set_CertId(int(external_id))

        response = self.client.do_action_with_exception(request)
        data = json.loads(response)

        return ProviderCertificate(
            external_id=external_id,
            subject_cn=data.get('CommonName', ''),
            serial_hex=data.get('SerialNo', ''),
            not_before=self._parse_date(data.get('StartDate')),
            not_after=self._parse_date(data.get('EndDate')),
            cert_pem=data.get('Cert'),
            status=self._map_status(data.get('Status'))
        )

    async def download_certificate(self, external_id: str) -> ProviderCertificate:
        """下载证书内容"""
        request = DownloadCertificateRequest.DownloadCertificateRequest()
        request.set_CertId(int(external_id))

        response = self.client.do_action_with_exception(request)
        data = json.loads(response)

        # 阿里云返回的证书可能是 base64 编码
        cert_pem = self._decode_pem(data.get('Cert'))
        key_pem = self._decode_pem(data.get('Key'))

        cert = await self.get_certificate(external_id)
        cert.cert_pem = cert_pem
        cert.key_pem = key_pem

        return cert

    async def renew_certificate(self, external_id: str) -> str:
        """续期证书 - 阿里云证书续期需要在控制台操作或通过订单流程"""
        # 阿里云证书续期较复杂，可能需要重新购买
        raise NotImplementedError("Aliyun certificate renewal requires console operation")

    def validate_credentials(self) -> bool:
        """验证凭据"""
        try:
            request = DescribeUserCertificateListRequest.DescribeUserCertificateListRequest()
            request.set_ShowSize(1)
            request.set_CurrentPage(1)
            self.client.do_action_with_exception(request)
            return True
        except Exception:
            return False

    def _parse_date(self, date_str: str) -> datetime:
        """解析阿里云日期格式"""
        if not date_str:
            return datetime.utcnow()
        # 格式: "2026-04-09 00:00:00"
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")

    def _map_status(self, status: str) -> str:
        """映射阿里云状态"""
        mapping = {
            'ISSUED': 'issued',
            'EXPIRED': 'expired',
            'REVOKED': 'revoked',
            'PENDING': 'pending',
        }
        return mapping.get(status, 'issued')

    def _decode_pem(self, content: str) -> str:
        """解码 PEM 内容"""
        if not content:
            return ''
        if '-----BEGIN' in content:
            return content
        try:
            return base64.b64decode(content).decode('utf-8')
        except Exception:
            return content


# Provider 注册表
PROVIDERS = {
    'aliyun-cas': AliyunCASProvider,
    # 后续扩展:
    # 'letsencrypt': LetsEncryptProvider,
    # 'internal-pki': InternalPKIProvider,
}


def get_provider(provider_type: str, config: dict) -> CertificateProviderBase:
    """获取 Provider 实例"""
    provider_cls = PROVIDERS.get(provider_type)
    if not provider_cls:
        raise ValueError(f"Unknown provider type: {provider_type}")
    return provider_cls(config)
```

---

## 5. 同步服务设计

### 5.1 同步调度器

```python
# server/app/services/provider_sync.py

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from app.models import CertificateProvider, ExternalCertificate
from app.providers import get_provider
from app.core.crypto import encrypt_value
from app.core.logging import get_logger

logger = get_logger(__name__)


class ProviderSyncService:
    """Provider 证书同步服务"""

    def __init__(self, db: Session):
        self.db = db

    async def sync_provider(self, provider_id: int) -> dict:
        """同步指定 Provider 的证书"""
        provider = self.db.query(CertificateProvider).filter_by(id=provider_id).first()
        if not provider:
            raise ValueError(f"Provider not found: {provider_id}")

        if not provider.sync_enabled:
            logger.info(f"Provider {provider.name} sync disabled, skipping")
            return {"status": "skipped", "reason": "sync_disabled"}

        # 解密凭据
        credentials = self._decrypt_credentials(provider.credentials_encrypted)

        # 获取 Provider 实例
        provider_instance = get_provider(provider.provider_type, credentials)

        # 验证凭据
        if not provider_instance.validate_credentials():
            logger.error(f"Provider {provider.name} credentials invalid")
            return {"status": "error", "reason": "invalid_credentials"}

        try:
            # 获取证书列表
            certs = await provider_instance.list_certificates()

            synced = 0
            updated = 0
            errors = 0

            for cert in certs:
                try:
                    result = await self._sync_certificate(
                        provider, cert, provider_instance
                    )
                    if result == "created":
                        synced += 1
                    elif result == "updated":
                        updated += 1
                except Exception as e:
                    logger.error(f"Failed to sync certificate {cert.external_id}: {e}")
                    errors += 1

            # 更新同步时间
            provider.last_sync_at = datetime.utcnow()
            self.db.commit()

            logger.info(f"Provider {provider.name} sync completed: {synced} new, {updated} updated, {errors} errors")

            return {
                "status": "success",
                "synced": synced,
                "updated": updated,
                "errors": errors
            }

        except Exception as e:
            logger.error(f"Provider {provider.name} sync failed: {e}")
            return {"status": "error", "reason": str(e)}

    async def _sync_certificate(
        self,
        provider: CertificateProvider,
        cert: 'ProviderCertificate',
        provider_instance
    ) -> str:
        """同步单个证书"""
        # 查找现有证书
        existing = self.db.query(ExternalCertificate).filter_by(
            provider=provider.name,
            external_id=cert.external_id
        ).first()

        if existing:
            # 更新元数据
            existing.subject_cn = cert.subject_cn
            existing.serial_hex = cert.serial_hex
            existing.not_before = cert.not_before
            existing.not_after = cert.not_after
            existing.last_sync_at = datetime.utcnow()
            existing.sync_status = "synced"
            self.db.commit()
            return "updated"
        else:
            # 创建新证书记录 (不下载内容，按需下载)
            new_cert = ExternalCertificate(
                provider=provider.name,
                provider_id=provider.id,
                external_id=cert.external_id,
                subject_cn=cert.subject_cn,
                serial_hex=cert.serial_hex,
                not_before=cert.not_before,
                not_after=cert.not_after,
                cert_pem="",  # 按需下载
                encrypted_key="",
                is_active=cert.status == "issued",
                sync_status="synced",
                last_sync_at=datetime.utcnow()
            )
            self.db.add(new_cert)
            self.db.commit()
            return "created"

    async def download_certificate_content(
        self,
        cert_id: int
    ) -> ExternalCertificate:
        """下载证书内容 (含私钥)"""
        cert = self.db.query(ExternalCertificate).filter_by(id=cert_id).first()
        if not cert:
            raise ValueError(f"Certificate not found: {cert_id}")

        if not cert.provider_id:
            raise ValueError("Certificate has no associated provider")

        provider = self.db.query(CertificateProvider).filter_by(
            id=cert.provider_id
        ).first()

        credentials = self._decrypt_credentials(provider.credentials_encrypted)
        provider_instance = get_provider(provider.provider_type, credentials)

        # 下载证书内容
        downloaded = await provider_instance.download_certificate(cert.external_id)

        # 更新证书
        cert.cert_pem = downloaded.cert_pem
        if downloaded.key_pem:
            cert.encrypted_key = encrypt_value(downloaded.key_pem)

        self.db.commit()
        return cert

    def _decrypt_credentials(self, encrypted: str) -> dict:
        """解密 Provider 凭据"""
        if not encrypted:
            return {}
        from app.core.crypto import decrypt_value
        return json.loads(decrypt_value(encrypted))


# 定时任务入口
async def sync_all_providers():
    """同步所有启用的 Provider"""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        service = ProviderSyncService(db)

        providers = db.query(CertificateProvider).filter_by(
            sync_enabled=True
        ).all()

        for provider in providers:
            # 检查是否需要同步
            if provider.last_sync_at:
                next_sync = provider.last_sync_at + timedelta(seconds=provider.sync_interval)
                if datetime.utcnow() < next_sync:
                    continue

            await service.sync_provider(provider.id)
    finally:
        db.close()
```

### 5.2 调度配置

```python
# server/app/main.py (添加到调度器)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.services.provider_sync import sync_all_providers

scheduler = AsyncIOScheduler()

# 每 30 分钟同步一次
scheduler.add_job(
    sync_all_providers,
    'interval',
    minutes=30,
    id='provider_sync',
    replace_existing=True
)
```

---

## 6. Control API 扩展

### 6.1 Provider 管理 API

```python
# server/app/api/providers.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models import CertificateProvider
from app.core.crypto import encrypt_value

router = APIRouter(prefix="/api/control/providers", tags=["providers"])


class ProviderCreate(BaseModel):
    name: str
    provider_type: str  # aliyun-cas, letsencrypt, internal-pki
    credentials: dict  # AccessKey 等，将被加密存储
    sync_enabled: bool = True
    sync_interval: int = 3600
    auto_renew_enabled: bool = False
    renew_before_days: int = 30


class ProviderResponse(BaseModel):
    id: int
    name: str
    provider_type: str
    sync_enabled: bool
    sync_interval: int
    auto_renew_enabled: bool
    renew_before_days: int
    last_sync_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.post("", response_model=ProviderResponse)
async def create_provider(
    data: ProviderCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_admin_api_key)
):
    """创建 Provider 配置"""
    # 检查名称唯一
    existing = db.query(CertificateProvider).filter_by(name=data.name).first()
    if existing:
        raise HTTPException(400, f"Provider {data.name} already exists")

    # 加密凭据
    credentials_encrypted = encrypt_value(json.dumps(data.credentials))

    provider = CertificateProvider(
        name=data.name,
        provider_type=data.provider_type,
        credentials_encrypted=credentials_encrypted,
        sync_enabled=data.sync_enabled,
        sync_interval=data.sync_interval,
        auto_renew_enabled=data.auto_renew_enabled,
        renew_before_days=data.renew_before_days,
    )

    db.add(provider)
    db.commit()
    db.refresh(provider)

    return provider


@router.post("/{provider_id}/sync")
async def trigger_sync(
    provider_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_admin_api_key)
):
    """手动触发同步"""
    from app.services.provider_sync import ProviderSyncService

    service = ProviderSyncService(db)
    result = await service.sync_provider(provider_id)

    return result


@router.post("/{provider_id}/validate")
async def validate_credentials(
    provider_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_admin_api_key)
):
    """验证 Provider 凭据"""
    provider = db.query(CertificateProvider).filter_by(id=provider_id).first()
    if not provider:
        raise HTTPException(404, "Provider not found")

    from app.providers import get_provider
    from app.core.crypto import decrypt_value

    credentials = json.loads(decrypt_value(provider.credentials_encrypted))
    provider_instance = get_provider(provider.provider_type, credentials)

    valid = provider_instance.validate_credentials()

    return {"valid": valid}


@router.get("", response_model=List[ProviderResponse])
async def list_providers(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_admin_api_key)
):
    """列出所有 Provider"""
    return db.query(CertificateProvider).all()


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_admin_api_key)
):
    """删除 Provider 配置"""
    provider = db.query(CertificateProvider).filter_by(id=provider_id).first()
    if not provider:
        raise HTTPException(404, "Provider not found")

    db.delete(provider)
    db.commit()

    return {"status": "deleted"}
```

### 6.2 注册路由

```python
# server/app/main.py

from app.api.providers import router as providers_router
app.include_router(providers_router)
```

---

## 7. 前端界面扩展

### 7.1 Provider 管理页面

```tsx
// server/frontend/src/pages/ProvidersPage.tsx

import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Select, Switch, message } from 'antd';

interface Provider {
  id: number;
  name: string;
  provider_type: string;
  sync_enabled: boolean;
  sync_interval: number;
  auto_renew_enabled: boolean;
  renew_before_days: number;
  last_sync_at: string | null;
}

export const ProvidersPage: React.FC = () => {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [form] = Form.useForm();

  const fetchProviders = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/control/providers', {
        headers: { 'X-Admin-API-Key': localStorage.getItem('apiKey') || '' }
      });
      const data = await response.json();
      setProviders(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProviders();
  }, []);

  const handleCreate = async (values: any) => {
    try {
      await fetch('/api/control/providers', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-API-Key': localStorage.getItem('apiKey') || ''
        },
        body: JSON.stringify(values)
      });
      message.success('Provider created');
      setModalVisible(false);
      fetchProviders();
    } catch (error) {
      message.error('Failed to create provider');
    }
  };

  const handleSync = async (providerId: number) => {
    try {
      await fetch(`/api/control/providers/${providerId}/sync`, {
        method: 'POST',
        headers: { 'X-Admin-API-Key': localStorage.getItem('apiKey') || '' }
      });
      message.success('Sync triggered');
    } catch (error) {
      message.error('Sync failed');
    }
  };

  return (
    <div>
      <div className="mb-4">
        <Button type="primary" onClick={() => setModalVisible(true)}>
          添加 Provider
        </Button>
      </div>

      <Table dataSource={providers} rowKey="id" loading={loading}>
        <Table.Column title="名称" dataIndex="name" key="name" />
        <Table.Column title="类型" dataIndex="provider_type" key="provider_type" />
        <Table.Column
          title="同步状态"
          dataIndex="sync_enabled"
          render={(v) => v ? '已启用' : '已禁用'}
        />
        <Table.Column
          title="最后同步"
          dataIndex="last_sync_at"
          render={(v) => v ? new Date(v).toLocaleString() : '-'}
        />
        <Table.Column
          title="操作"
          render={(_, record) => (
            <Button size="small" onClick={() => handleSync(record.id)}>
              立即同步
            </Button>
          )}
        />
      </Table>

      <Modal
        title="添加 Provider"
        open={modalVisible}
        onOk={() => form.submit()}
        onCancel={() => setModalVisible(false)}
      >
        <Form form={form} onFinish={handleCreate} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="aliyun-prod" />
          </Form.Item>
          <Form.Item name="provider_type" label="类型" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="aliyun-cas">阿里云 SSL 证书</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name={['credentials', 'access_key_id']} label="Access Key ID" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name={['credentials', 'access_key_secret']} label="Access Key Secret" rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name={['credentials', 'region']} label="区域">
            <Input defaultValue="cn-hangzhou" />
          </Form.Item>
          <Form.Item name="sync_enabled" label="启用同步" valuePropName="checked">
            <Switch defaultChecked />
          </Form.Item>
          <Form.Item name="auto_renew_enabled" label="自动续期" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};
```

---

## 8. 安全考量

### 8.1 AccessKey 保护

- **加密存储**: Provider 凭据使用 Fernet 加密后存入数据库
- **RAM 最小权限**: 仅授予 `AliyunCASReadOnlyAccess`，避免 `AliyunCASFullAccess`
- **IP 白名单**: 在阿里云 RAM 中配置 IP 白名单限制

### 8.2 私钥传输

- 阿里云下载的私钥通过 HTTPS 传输
- 控制平面存储时使用 Fernet 加密
- Agent 拉取时通过 mTLS 通道传输

### 8.3 审计日志

所有 Provider 操作记录到 `audit_logs`:
- 创建/删除 Provider
- 同步证书
- 下载证书内容

---

## 9. 实施计划

### 9.1 阶段一: Provider 基础设施 (1 周)

- [ ] 数据库迁移 (CertificateProvider 表)
- [ ] Provider 抽象层实现
- [ ] 阿里云 Provider 实现
- [ ] 单元测试

### 9.2 阶段二: 同步服务 (1 周)

- [ ] 同步服务实现
- [ ] 定时调度集成
- [ ] 错误处理和重试
- [ ] 集成测试

### 9.3 阶段三: Control API (1 周)

- [ ] Provider 管理 API
- [ ] 手动同步 API
- [ ] 凭据验证 API
- [ ] API 文档

### 9.4 阶段四: 前端界面 (1 周)

- [ ] Provider 管理页面
- [ ] 证书同步状态展示
- [ ] 同步操作按钮
- [ ] E2E 测试

### 9.5 阶段五: 自动续期 (2 周)

- [ ] 续期逻辑实现
- [ ] 到期预警集成
- [ ] 续期失败告警
- [ ] 端到端测试

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 阿里云 API 变更 | Provider 失效 | 版本锁定 SDK，监控 API 响应 |
| AccessKey 泄露 | 证书泄露 | RAM 最小权限 + IP 白名单 + 定期轮换 |
| 同步失败 | 证书过期 | 告警通知 + 降级手动上传 |
| 私钥传输不安全 | 中间人攻击 | HTTPS + mTLS Agent 通信 |

---

## 11. 后续扩展

完成阿里云集成后，可按相同模式扩展:

1. **Let's Encrypt**: ACME 协议自动签发
2. **腾讯云 SSL 证书**: 类似阿里云实现
3. **内部 PKI**: 对接企业内部 CA

---

## 附录 A: 阿里云 RAM 权限配置

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cas:DescribeUserCertificateList",
        "cas:DescribeUserCertificateDetail",
        "cas:DownloadCertificate"
      ],
      "Resource": "*"
    }
  ]
}
```

## 附录 B: 环境变量

```bash
# Provider 凭据加密密钥 (复用现有的 CA_KEY_ENCRYPTION_KEY)
CA_KEY_ENCRYPTION_KEY=your-fernet-key

# 同步间隔 (秒)
PROVIDER_SYNC_INTERVAL=3600

# 同步并发数
PROVIDER_SYNC_CONCURRENCY=5
```

---

_文档版本: 1.0_
_创建日期: 2026-04-09_
_目标里程碑: Phase 4 (M5)_
