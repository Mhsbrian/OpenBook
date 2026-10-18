// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
package org.openbook.test.gsf;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;

/** ANAL-211 synthetic test package: answers gservices queries for android_id with a fixed, fake ID. */
public class Gservices extends ContentProvider {
    /** Not any device's ID: a fixed test value (the decimal digits of pi), so a test can check what is shown. */
    public static final String FAKE_ANDROID_ID = "3141592653589793238";

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        MatrixCursor c = new MatrixCursor(new String[] {"key", "value"});
        if (args != null) {
            for (String k : args) {
                if ("android_id".equals(k)) c.addRow(new Object[] {k, FAKE_ANDROID_ID});
            }
        }
        return c;
    }

    @Override
    public String getType(Uri uri) {
        return null;
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        return null;
    }

    @Override
    public int delete(Uri uri, String selection, String[] args) {
        return 0;
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] args) {
        return 0;
    }
}
