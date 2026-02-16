FROM node:18-alpine
WORKDIR /app
COPY web/package.json web/next.config.js /app/
RUN npm install
COPY web/app /app/app
ENV PORT=3000
EXPOSE 3000
CMD ["npm", "run", "dev"]
