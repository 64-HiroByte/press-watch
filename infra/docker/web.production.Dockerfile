FROM node:24.22.2-bookworm-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS build
WORKDIR /workspace
ENV NEXT_TELEMETRY_DISABLED=1 PRESSWATCH_STANDALONE=1
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN corepack enable pnpm && corepack install && pnpm install --filter @press-watch/web... --frozen-lockfile
COPY apps/web/app apps/web/app
COPY apps/web/components apps/web/components
COPY apps/web/lib apps/web/lib
COPY apps/web/mock apps/web/mock
COPY apps/web/public apps/web/public
COPY apps/web/next.config.ts apps/web/tsconfig.json apps/web/postcss.config.mjs apps/web/components.json apps/web/
RUN pnpm build:web

FROM node:24.22.2-bookworm-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS runtime
WORKDIR /workspace
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /workspace/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /workspace/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=node:node /workspace/apps/web/public ./apps/web/public
USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
