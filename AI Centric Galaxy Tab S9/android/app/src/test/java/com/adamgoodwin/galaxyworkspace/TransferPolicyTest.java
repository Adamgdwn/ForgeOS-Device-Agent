package com.adamgoodwin.galaxyworkspace;

import org.junit.Test;
import static org.junit.Assert.*;

public class TransferPolicyTest {
    @Test public void onlyExactOriginExportEndpointsCanDownload() {
        String origin = "http://localhost:4318";
        String path = "/api/exports/11111111-1111-4111-8111-111111111111/download";
        assertTrue(TransferPolicy.exportUrl(origin, origin + path));
        for (String url : new String[] { "https://example.com" + path, origin + "/api/bootstrap", origin + path + "?redirect=x", origin + path + "#fragment", "file:///etc/passwd", origin + "/api/exports/../download" })
            assertFalse(url, TransferPolicy.exportUrl(origin, url));
    }
    @Test public void pickerCannotExposeAppPrivateOrArbitraryFilePaths() {
        String app = "com.adamgoodwin.galaxyworkspace";
        assertTrue(TransferPolicy.selectedContent("content://com.android.providers.downloads.documents/document/42", app));
        for (String uri : new String[] { "file:///data/data/" + app + "/cookies", "https://example.com/file", "content://" + app + ".provider/private", "content:///missing-authority" })
            assertFalse(uri, TransferPolicy.selectedContent(uri, app));
        assertNull(TransferPolicy.mime("text/html"));
        assertEquals("text/markdown", TransferPolicy.mime("text/markdown; charset=utf-8"));
    }
    @Test public void reportNamesAreReadableAndCannotContainPaths() {
        assertEquals("Meeting report.pdf", TransferPolicy.filename("attachment; filename*=UTF-8''Meeting%20report.pdf", "application/pdf"));
        assertEquals("Summary report.docx", TransferPolicy.filename(null, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"));
        assertFalse(TransferPolicy.filename("attachment; filename=\"../../escape.md\"", "text/markdown").contains("/"));
    }
}
