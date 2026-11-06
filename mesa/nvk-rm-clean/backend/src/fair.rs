//! A first-come, first-served mutex for the Bridge state (ANAL-345).
//!
//! `std::sync::Mutex` makes no fairness promise: a thread that releases the
//! lock and asks for it again at once usually gets it back before a waiter
//! that was woken. When several threads call into the backend in tight loops
//! (allocations, CPU maps and frees on three threads), a fourth thread's
//! free or submit could wait behind hundreds of short critical sections.
//! Measured with `mesa::reclaim_tests::concurrent_alloc_free_gated_submit_stress`
//! on the RTX 4090: the waiting thread was blocked 80-100 ms while every holder
//! kept the lock for about 2 us. The RTX 5070 Ti Laptop host reached 630 ms.
//!
//! `FairMutex` hands the lock out in ticket order: `lock` takes the next
//! ticket and waits until it is served, so a thread waits at most for the
//! critical sections of the threads that asked before it. The data stays in
//! a `std::sync::Mutex`, which still provides the happens-before between
//! successive owners; the ticket gate only orders who takes it next, so that
//! inner mutex is never contended. Poisoning is ignored, as `Bridge::lock`
//! already did: the state stays usable for teardown after a panic.
use std::{
    ops::{Deref, DerefMut},
    sync::{Condvar, Mutex, MutexGuard, TryLockError},
};

#[derive(Default)]
struct Tickets {
    /// The ticket the next `lock` takes.
    next: u64,
    /// The ticket that may own the data now.
    serving: u64,
    /// Threads blocked in `lock` (no wake-up call when none).
    waiting: u32,
}

pub(crate) struct FairMutex<T> {
    data: Mutex<T>,
    tickets: Mutex<Tickets>,
    turn: Condvar,
}

pub(crate) struct FairGuard<'a, T> {
    /// `None` only inside `drop`.
    data: Option<MutexGuard<'a, T>>,
    lock: &'a FairMutex<T>,
}

impl<T> FairMutex<T> {
    pub(crate) fn new(value: T) -> Self {
        Self {
            data: Mutex::new(value),
            tickets: Mutex::new(Tickets::default()),
            turn: Condvar::new(),
        }
    }
    fn tickets(&self) -> MutexGuard<'_, Tickets> {
        self.tickets.lock().unwrap_or_else(|p| p.into_inner())
    }
    fn data(&self) -> MutexGuard<'_, T> {
        self.data.lock().unwrap_or_else(|p| p.into_inner())
    }
    /// Wait for this caller's turn, in arrival order.
    pub(crate) fn lock(&self) -> FairGuard<'_, T> {
        let mut tickets = self.tickets();
        let ticket = tickets.next;
        tickets.next += 1;
        if tickets.serving != ticket {
            tickets.waiting += 1;
            while tickets.serving != ticket {
                tickets = self.turn.wait(tickets).unwrap_or_else(|p| p.into_inner());
            }
            tickets.waiting -= 1;
        }
        drop(tickets);
        // The previous owner released `data` before serving this ticket, and
        // no other caller can reach it until this guard drops.
        FairGuard {
            data: Some(self.data()),
            lock: self,
        }
    }
    /// The lock only if nobody holds it or waits for it.
    pub(crate) fn try_lock(&self) -> Option<FairGuard<'_, T>> {
        let mut tickets = self.tickets();
        if tickets.serving != tickets.next {
            return None;
        }
        let data = match self.data.try_lock() {
            Ok(data) => data,
            Err(TryLockError::Poisoned(p)) => p.into_inner(),
            // No ticket is outstanding, so nobody holds `data`.
            Err(TryLockError::WouldBlock) => return None,
        };
        tickets.next += 1;
        Some(FairGuard {
            data: Some(data),
            lock: self,
        })
    }
}

impl<T> Drop for FairGuard<'_, T> {
    fn drop(&mut self) {
        // Release the data first: the next ticket's owner takes it at once.
        drop(self.data.take());
        let mut tickets = self.lock.tickets();
        tickets.serving += 1;
        let wake = tickets.waiting != 0;
        drop(tickets);
        if wake {
            self.lock.turn.notify_all();
        }
    }
}

impl<T> Deref for FairGuard<'_, T> {
    type Target = T;
    fn deref(&self) -> &T {
        self.data.as_ref().unwrap()
    }
}

impl<T> DerefMut for FairGuard<'_, T> {
    fn deref_mut(&mut self) -> &mut T {
        self.data.as_mut().unwrap()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        sync::{
            atomic::{AtomicBool, Ordering},
            Arc,
        },
        thread,
        time::{Duration, Instant},
    };

    #[test]
    fn try_lock_refuses_while_held_or_queued() {
        let m = Arc::new(FairMutex::new(0u32));
        let held = m.lock();
        assert!(m.try_lock().is_none());
        let waiter = {
            let m = Arc::clone(&m);
            thread::spawn(move || *m.lock() += 1)
        };
        while m.tickets().waiting == 0 {
            thread::yield_now();
        }
        drop(held);
        waiter.join().unwrap();
        assert_eq!(*m.try_lock().unwrap(), 1);
    }

    #[test]
    fn poisoned_state_stays_usable() {
        let m = Arc::new(FairMutex::new(5u32));
        let m2 = Arc::clone(&m);
        let _ = thread::spawn(move || {
            let _g = m2.lock();
            panic!("poison");
        })
        .join();
        assert_eq!(*m.lock(), 5);
        assert_eq!(*m.try_lock().unwrap(), 5);
    }

    /// Three threads re-take the lock in tight loops; a fourth must still get
    /// it within a bound set by their short critical sections.
    #[test]
    fn a_waiter_is_not_starved_by_tight_loops() {
        let m = Arc::new(FairMutex::new(0u64));
        let stop = Arc::new(AtomicBool::new(false));
        let spinners: Vec<_> = (0..3)
            .map(|_| {
                let (m, stop) = (Arc::clone(&m), Arc::clone(&stop));
                thread::spawn(move || {
                    while !stop.load(Ordering::Relaxed) {
                        let mut g = m.lock();
                        *g += 1;
                        let t = Instant::now();
                        while t.elapsed() < Duration::from_micros(2) {}
                    }
                })
            })
            .collect();
        let mut worst = Duration::ZERO;
        for _ in 0..2000 {
            let t = Instant::now();
            drop(m.lock());
            worst = worst.max(t.elapsed());
        }
        stop.store(true, Ordering::Relaxed);
        for s in spinners {
            s.join().unwrap();
        }
        assert!(worst < Duration::from_millis(50), "worst wait {worst:?}");
    }
}
