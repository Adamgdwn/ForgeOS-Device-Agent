package com.adamgoodwin.galaxyworkspace;

import org.junit.Test;
import static org.junit.Assert.*;

public class WorkspaceAddressTest {
    @Test public void acceptsConfiguredSecureAndUsbOrigins() {
        assertEquals(WorkspaceAddress.USB, WorkspaceAddress.normalize(" http://localhost:4318/ "));
        assertEquals("https://host.example", WorkspaceAddress.normalize("HTTPS://HOST.example:443/"));
        assertEquals("https://host.example:444", WorkspaceAddress.normalize("https://host.example:444"));
    }

    @Test public void rejectsAmbiguousOrUnsafeSettings() {
        String[] invalid = {"http://example.com", "http://localhost:80", "http://127.0.0.1:4318",
            "https://user:password@host.example", "https://host.example/path", "https://host.example?token=x",
            "https://host.example/#secret", "file:///data/data", "javascript:alert(1)", "intent://host",
            "https://host.example:0", "https://host.example:65536", "https://host.example\\@evil.example",
            "https://", "", "host.example"};
        for (String url : invalid) {
            assertThrows(url, IllegalArgumentException.class, () -> WorkspaceAddress.normalize(url));
        }
    }

    @Test public void keepsNavigationOnTheExactOrigin() {
        String origin = "https://host.example";
        assertTrue(WorkspaceAddress.contains(origin, "https://host.example/#conversation-123"));
        assertTrue(WorkspaceAddress.contains(origin, "https://host.example:443/api/session"));
        String[] escaped = {"https://host.example.evil.test", "https://host.example@evil.test",
            "https://evil.test@host.example", "http://host.example", "https://host.example:444/",
            "file:///data", "javascript:alert(1)", "//host.example/path"};
        for (String url : escaped) assertFalse(url, WorkspaceAddress.contains(origin, url));
    }

    @Test public void permitsOnlyWebLinksOutsideTheWorkspace() {
        assertTrue(WorkspaceAddress.externalWebLink("https://microsoft.com/devicelogin"));
        assertFalse(WorkspaceAddress.externalWebLink("intent://settings"));
        assertFalse(WorkspaceAddress.externalWebLink("file:///sdcard/example"));
        assertFalse(WorkspaceAddress.externalWebLink("https://secret@host.example/"));
    }
}
