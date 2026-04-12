# harness-scaffold 仓库引导方案 v1.2

## 1. 目标

将当前需求工作流服务整理为一个真正可部署的新仓库，并保持与 `harness-scaffold` 的基础结构、CI/CD 和部署习惯一致。

## 2. 推荐方式

推荐不要直接在当前工作目录上补 `.git`，而是：

1. 先以 `harness-scaffold` 为底座生成一个新目录
2. 再把本仓库中已经完成的需求工作流服务 overlay 进去
3. 最后初始化新 GitHub 仓库并接现有 CI/CD secrets

## 3. 已准备好的脚本

已提供脚本：

- [bootstrap_repo_from_harness_scaffold.sh](../../scripts/bootstrap_repo_from_harness_scaffold.sh)

用法：

```bash
bash ./scripts/bootstrap_repo_from_harness_scaffold.sh \
  /path/to/harness-scaffold \
  /path/to/new-repo
```

## 4. overlay 内容

脚本会将以下内容带入新仓库：

- `services/coordinator-service`
- `src/requirement_workflow_v12`
- `docs`
- `docker`
- `deploy/customers`
- `.github/workflows`
- `README.md`
- `requirements.txt`

## 5. 新仓库后续动作

生成新仓库目录后，继续执行：

1. `git init`
2. `git remote add origin <new-repo-url>`
3. 推送默认分支
4. 在 GitHub 配置部署 secrets
5. 用 `deploy-coordinator-service.yml` 验证构建与部署

## 6. 部署前仍需补齐

- `FEISHU_CREATION_GROUP_CHAT_ID`
- `FEISHU_DOC_FOLDER_TOKEN`
- `FEISHU_VERIFICATION_TOKEN`
- `FEISHU_ENCRYPT_KEY`
- Bitable 新字段落库
- 文档 section rewrite 的真实写回
- OpenClaw author/reviewer 的结构化调用
