FROM node:24.22.2-bookworm-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS base
WORKDIR /workspace
ENV NEXT_TELEMETRY_DISABLED=1

FROM base AS dependencies
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN corepack enable pnpm \
    && corepack install \
    && pnpm install --filter @press-watch/web... --frozen-lockfile

FROM dependencies AS development
COPY apps/web apps/web
EXPOSE 3000
CMD ["pnpm", "--filter", "@press-watch/web", "dev", "--hostname", "0.0.0.0"]

FROM dependencies AS build
ENV NODE_ENV=production PRESSWATCH_STANDALONE=1
COPY apps/web apps/web
RUN pnpm build:web

FROM base AS production
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /workspace/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /workspace/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=node:node /workspace/apps/web/public ./apps/web/public
USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
