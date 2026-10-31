// Copyright (C) 2026 The OpenBook Authors
// SPDX-License-Identifier: Apache-2.0
package org.json
class JSONObject {
    private val data = mutableMapOf<String, Any>()
    fun put(k: String, v: Any): JSONObject { data[k] = v; return this }
    fun optString(k: String): String = data[k]?.toString() ?: ""
    fun optBoolean(k: String): Boolean = data[k] == true
    fun has(k: String): Boolean = data.containsKey(k)
    fun getInt(k: String): Int = (data[k] as Number).toInt()
    fun optLong(k: String): Long = (data[k] as? Number)?.toLong() ?: 0
}
