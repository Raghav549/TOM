package com.tom.device

import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicLong

/** Small observable event store used by the TOM companion UI. */
object TomLiveActivityStore {
    data class Item(
        val sequence: Long,
        val type: String,
        val title: String,
        val detail: String,
        val terminal: Boolean = false,
    )

    private val sequence = AtomicLong(0)
    private val items = CopyOnWriteArrayList<Item>()
    private val listeners = CopyOnWriteArrayList<(Item) -> Unit>()

    fun add(type: String, title: String, detail: String, terminal: Boolean = false) {
        val item = Item(sequence.incrementAndGet(), type, title, detail, terminal)
        items.add(item)
        while (items.size > 100) items.removeAt(0)
        listeners.forEach { listener -> runCatching { listener(item) } }
    }

    fun recent(): List<Item> = items.toList()

    fun subscribe(listener: (Item) -> Unit) {
        listeners += listener
    }

    fun unsubscribe(listener: (Item) -> Unit) {
        listeners -= listener
    }

    fun clear() = items.clear()
}
