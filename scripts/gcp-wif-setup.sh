#!/usr/bin/env bash
# ============================================================
# GCP Workload Identity Federation 一次性設定腳本
# 用途：讓 GitHub Actions 免金鑰存取 Cloud Run 部署權限
#
# 執行方式：
#   1. 開啟 https://shell.cloud.google.com
#   2. 貼上此腳本並執行
#   3. 將輸出的兩個值設為 GitHub Secrets
# ============================================================

set -euo pipefail

PROJECT_ID="eternal-insight-423516-m3"
GITHUB_ORG="R300-AI"
GITHUB_REPO="Agentic-SDK"
POOL_ID="github-pool"
PROVIDER_ID="github-provider"
SA_NAME="github-action-service"

echo "==> 切換到專案 ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}"

echo "==> 取得 Project Number"
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
echo "    Project Number: ${PROJECT_NUMBER}"

echo "==> 啟用必要 APIs（首次約需 1-2 分鐘）"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com

echo "==> 建立 Service Account（已存在則跳過）"
gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="GitHub Actions Runner" \
  --project="${PROJECT_ID}" 2>&1 | grep -v "already exists" || true

SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "==> 授予 SA 所需角色"
for ROLE in \
  roles/run.admin \
  roles/cloudbuild.builds.editor \
  roles/artifactregistry.admin \
  roles/storage.admin \
  roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --quiet
done

echo "==> 建立 Workload Identity Pool"
gcloud iam workload-identity-pools create "${POOL_ID}" \
  --location="global" \
  --display-name="GitHub Actions Pool" \
  --project="${PROJECT_ID}" 2>/dev/null || echo "    Pool 已存在，跳過"

echo "==> 建立 GitHub OIDC Provider"
gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_ID}" \
  --location="global" \
  --workload-identity-pool="${POOL_ID}" \
  --display-name="GitHub Provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GITHUB_ORG}/${GITHUB_REPO}'" \
  --project="${PROJECT_ID}" 2>/dev/null || echo "    Provider 已存在，跳過"

echo "==> 綁定 WIF 與 SA（允許此 repo 的 GitHub Actions 扮演 SA）"
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${GITHUB_ORG}/${GITHUB_REPO}" \
  --project="${PROJECT_ID}"

WIF_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}"

echo ""
echo "======================================================"
echo "設定完成！請將以下兩個值設為 GitHub Secrets："
echo ""
echo "  Secret 名稱         → 值"
echo "  ─────────────────────────────────────────────────"
echo "  WIF_PROVIDER        → ${WIF_PROVIDER}"
echo "  WIF_SA_EMAIL        → ${SA_EMAIL}"
echo ""
echo "GitHub Secrets 頁面："
echo "  https://github.com/${GITHUB_ORG}/${GITHUB_REPO}/settings/secrets/actions"
echo "======================================================"
