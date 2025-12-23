#
# Dockerfile - nginx for Leafy Media (Kanopy)
# Main container serving static files and proxying to Flask sidecar
#

FROM nginx:alpine

# Copy nginx configuration
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Copy static files from Flask app
COPY app/static /app/static

# Kanopy requires port 8080
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
