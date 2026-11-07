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

  return project("brilliant-compassion", {
    resources: [api, web],
  });
});
