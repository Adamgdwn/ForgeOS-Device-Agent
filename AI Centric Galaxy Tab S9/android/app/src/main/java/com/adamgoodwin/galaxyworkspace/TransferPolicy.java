package com.adamgoodwin.galaxyworkspace;

import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** File transfers are limited to user-picked content URIs and authenticated report exports. */
final class TransferPolicy {
    static boolean exportUrl(String origin, String url) {
        if (!WorkspaceAddress.contains(origin, url)) return false;
        try {
            URI uri = URI.create(url);
            return uri.getRawQuery() == null && uri.getRawFragment() == null
                && uri.getRawPath().matches("/api/exports/[0-9a-f-]{36}/download");
        } catch (IllegalArgumentException ignored) { return false; }
    }
    static boolean selectedContent(String uri, String packageName) {
        try {
            URI value = URI.create(uri);
            String authority = value.getAuthority();
            return "content".equals(value.getScheme()) && authority != null && !authority.isBlank()
                && !authority.equals(packageName) && !authority.startsWith(packageName + ".");
        } catch (IllegalArgumentException ignored) { return false; }
    }
    static boolean documentUrl(String origin, String url) {
        if (exportUrl(origin, url)) return true;
        if (!WorkspaceAddress.contains(origin, url)) return false;
        try {
            URI uri = URI.create(url);
            return uri.getRawFragment() == null
                && uri.getRawPath().matches("/api/(projects|conversations)/[0-9a-f-]{36}/download")
                && uri.getRawQuery() != null && uri.getRawQuery().matches("path=[^&]+")
                && !URLDecoder.decode(uri.getRawQuery().substring(5), StandardCharsets.UTF_8).contains("\u0000");
        } catch (IllegalArgumentException ignored) { return false; }
    }
    static String mime(String value) {
        String type = value == null ? "" : value.split(";", 2)[0].trim();
        return switch (type) {
            case "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "text/plain", "text/markdown", "text/csv", "text/tab-separated-values", "application/json", "message/rfc822" -> type;
            default -> null;
        };
    }
    static String filename(String disposition, String type) {
        String name = "Summary report";
        Matcher encoded = Pattern.compile("filename\\*=UTF-8''([^;]+)", Pattern.CASE_INSENSITIVE).matcher(disposition == null ? "" : disposition);
        Matcher plain = Pattern.compile("filename=\"([^\"]+)\"", Pattern.CASE_INSENSITIVE).matcher(disposition == null ? "" : disposition);
        try {
            if (encoded.find()) name = URLDecoder.decode(encoded.group(1), StandardCharsets.UTF_8);
            else if (plain.find()) name = plain.group(1);
        } catch (IllegalArgumentException ignored) { name = "Summary report"; }
        name = name.replaceAll("[^\\p{L}\\p{N} ._-]", "_").replaceAll("^[. ]+|[. ]+$", "");
        if (name.length() > 160) name = name.substring(0, 160);
        if (name.isBlank()) name = "Summary report";
        String extension = switch (type) {
            case "application/pdf" -> ".pdf";
            case "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" -> ".xlsx";
            case "application/vnd.openxmlformats-officedocument.presentationml.presentation" -> ".pptx";
            case "text/plain" -> ".txt";
            case "text/markdown" -> ".md";
            case "text/csv" -> ".csv";
            case "text/tab-separated-values" -> ".tsv";
            case "application/json" -> ".json";
            case "message/rfc822" -> ".eml";
            default -> ".docx";
        };
        return name.toLowerCase(java.util.Locale.ROOT).endsWith(extension) ? name : name + extension;
    }
}
