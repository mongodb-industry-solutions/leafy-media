#
# Copyright (c) 2024, 2025 MongoDB Inc.
# Author: Benjamin Lorenz <benjamin.lorenz@mongodb.com>
#

from flask import render_template, request, jsonify
from . import main
import logging
import traceback

logger = logging.getLogger(__name__)


@main.app_errorhandler(403)
def forbidden(e):
    if request.accept_mimetypes.accept_json and \
            not request.accept_mimetypes.accept_html:
        response = jsonify({'error': 'forbidden'})
        response.status_code = 403
        return response
    return render_template('403.html'), 403


@main.app_errorhandler(404)
def page_not_found(e):
    if request.accept_mimetypes.accept_json and \
            not request.accept_mimetypes.accept_html:
        response = jsonify({'error': 'not found'})
        response.status_code = 404
        return response
    return render_template('404.html'), 404


@main.app_errorhandler(500)
def internal_server_error(e):
    # Log the full exception with traceback
    logger.error(f"500 Error on {request.path}: {str(e)}")
    logger.error(f"Exception type: {type(e).__name__}")
    logger.error(f"Full traceback:\n{traceback.format_exc()}")
    print(f"[ERROR] 500 on {request.path}: {str(e)}", flush=True)
    print(f"[ERROR] Traceback:\n{traceback.format_exc()}", flush=True)

    if request.accept_mimetypes.accept_json and \
            not request.accept_mimetypes.accept_html:
        response = jsonify({'error': 'internal server error', 'detail': str(e)})
        response.status_code = 500
        return response
    return render_template('500.html'), 500


@main.app_errorhandler(Exception)
def handle_exception(e):
    # Catch-all for any unhandled exceptions
    logger.error(f"Unhandled exception on {request.path}: {str(e)}")
    logger.error(f"Exception type: {type(e).__name__}")
    logger.error(f"Full traceback:\n{traceback.format_exc()}")
    print(f"[ERROR] Unhandled exception on {request.path}: {str(e)}", flush=True)
    print(f"[ERROR] Type: {type(e).__name__}", flush=True)
    print(f"[ERROR] Traceback:\n{traceback.format_exc()}", flush=True)

    if request.accept_mimetypes.accept_json and \
            not request.accept_mimetypes.accept_html:
        response = jsonify({'error': 'internal server error', 'detail': str(e)})
        response.status_code = 500
        return response
    return render_template('500.html'), 500
