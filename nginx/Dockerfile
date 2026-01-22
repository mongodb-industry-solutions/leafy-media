#
# Dockerfile - nginx for Leafy Media (Kanopy)
# Main container serving static files and proxying to Flask sidecar
#

FROM nginx:alpine

# Copy nginx configuration
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Copy static files from Flask app
COPY app/static /app/static

# Copy additional images from templates (favicons, video howto images, etc.)
# These are served at /img/ via nginx
COPY app/templates/img /app/templates/img

# Copy video cover for default video player
COPY app/templates/video /app/templates/video

# Kanopy requires port 8080
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
