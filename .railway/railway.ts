import { defineRailway, github, preserve, project, service } from "railway/iac";

export default defineRailway(() => {
  const pressWatch = github("64-HiroByte/press-watch", { branch: "phase-7/operations" });

  const api = service("api", {
    source: pressWatch,
    build: { buildEnvironment: "V3", builder: "RAILPACK" },
    healthcheck: "/health",
    replicas: { iad: 1 },
    deploy: { ipv6EgressEnabled: true, restartPolicyType: "NEVER" },
    env: {
      DATABASE_URL: preserve(),
      HOST: preserve(),
      PORT: preserve(),
      PRESSWATCH_DB_CA_CERT: preserve(),
      RAILWAY_DOCKERFILE_PATH: preserve(),
    },
  });
  const web = service("web", {
    source: pressWatch,
    build: { buildEnvironment: "V3", builder: "RAILPACK" },
    healthcheck: "/health",
    replicas: { iad: 1 },
    deploy: { restartPolicyType: "NEVER" },
    env: {
      PRESSWATCH_API_BASE_URL: preserve(),
      PRESSWATCH_BASIC_AUTH_PASSWORD: preserve(),
      PRESSWATCH_BASIC_AUTH_USER: preserve(),
      RAILWAY_DOCKERFILE_PATH: preserve(),
    },
  });

  // 既存のAPI・Webに影響しないよう、設定変更はfetch-jobだけに適用する。
  const fetchJob = service("fetch-job", {
    build: {
      buildEnvironment: "V3",
      builder: "DOCKERFILE",
      dockerfilePath: "infra/docker/python.Dockerfile",
    },
    replicas: { iad: 1 },
    deploy: {
      ipv6EgressEnabled: true,
      restartPolicyType: "NEVER",
      drainingSeconds: 30,
      startCommand: "/app/.venv/bin/python -m press_watch_api.commands.run_fetch_job --url https://www.env.go.jp/press/index.html --archive-month-limit 6 --known-release-months 3 --verbose",
      cronSchedule: "30 1,7 * * *",
    },
    env: {
      DATABASE_URL: preserve(),
      PRESSWATCH_DB_CA_CERT: preserve(),
      PRESSWATCH_PYTHON_TARGET: "scheduled-job",
      RAILWAY_DOCKERFILE_PATH: "infra/docker/python.Dockerfile",
    },
  });

  return project("brilliant-compassion", {
    resources: [api, web, fetchJob],
  });
});
