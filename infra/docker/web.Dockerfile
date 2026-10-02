FROM node:24.21.0-bookworm-slim

WORKDIR /workspace

ENV NEXT_TELEMETRY_DISABLED=1

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json

RUN corepack enable pnpm \
    && corepack install \
    && pnpm --version \
    && COREPACK_ENABLE_NETWORK=0 pnpm --version

RUN pnpm install --filter @press-watch/web... --frozen-lockfile

COPY apps/web apps/web

EXPOSE 3000

CMD ["pnpm", "--filter", "@press-watch/web", "dev", "--hostname", "0.0.0.0"]
