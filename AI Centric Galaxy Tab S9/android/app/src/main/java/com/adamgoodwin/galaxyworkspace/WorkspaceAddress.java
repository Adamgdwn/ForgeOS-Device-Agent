package com.adamgoodwin.galaxyworkspace;

import java.net.URI;
import java.util.Locale;

/** One explicitly selected origin. Credentials and arbitrary HTTP hosts are never accepted. */
final class WorkspaceAddress {
    static final String USB = "http://localhost:4318";

    static String normalize(String input) {
        try {
            URI uri = new URI(input.trim());
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
            String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase(Locale.ROOT);
            if (host.isEmpty() || uri.getRawUserInfo() != null || uri.getRawQuery() != null
                    || uri.getRawFragment() != null || (uri.getRawPath() != null
                    && !uri.getRawPath().isEmpty() && !uri.getRawPath().equals("/"))) {
                throw new IllegalArgumentException();
            }
            if (scheme.equals("http") && host.equals("localhost") && uri.getPort() == 4318) return USB;
            if (!scheme.equals("https") || uri.getPort() == 0 || uri.getPort() > 65535) {
                throw new IllegalArgumentException();
            }
            return "https://" + host + (uri.getPort() == -1 || uri.getPort() == 443 ? "" : ":" + uri.getPort());
        } catch (Exception e) {
            throw new IllegalArgumentException("Use a full HTTPS address, or http://localhost:4318 for USB.");
        }
    }

    static boolean contains(String origin, String url) {
        try {
            URI uri = new URI(url);
            if (uri.getRawUserInfo() != null) return false;
            String authority = uri.getRawAuthority();
            return authority != null && normalize(uri.getScheme() + "://" + authority).equals(origin);
        } catch (Exception e) { return false; }
    }

    static boolean externalWebLink(String url) {
        try {
            URI uri = new URI(url);
            return uri.getHost() != null && uri.getRawUserInfo() == null
                && ("https".equalsIgnoreCase(uri.getScheme()) || "http".equalsIgnoreCase(uri.getScheme()));
        } catch (Exception e) { return false; }
    }
}
