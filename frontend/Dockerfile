FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# NEXT_PUBLIC_* vars are baked into the bundle at build time,
# so they must be present as env during `next build`, not just at runtime.
ARG NEXT_PUBLIC_API_URL=http://localhost:8001
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN npm run build

FROM node:22-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
# public/ not present yet; add COPY for /app/public when static assets appear

EXPOSE 3000

CMD ["npm", "start"]
