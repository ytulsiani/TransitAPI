package com.mbta.mbtaapi;

import com.google.common.cache.Cache;
import com.google.common.cache.CacheBuilder;
import java.io.IOException;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

public class StopService {
    private final MbtaClient mbtaClient;
    private final Cache<String, List<StopSummary>> cache;

    public StopService(MbtaClient mbtaClient) {
        this.mbtaClient = mbtaClient;
        this.cache =
                CacheBuilder.newBuilder()
                        .expireAfterWrite(5, TimeUnit.MINUTES)
                        .build();
    }

    public List<StopSummary> getStops(String routeId)
            throws ExecutionException, IOException, InterruptedException {
        if (routeId == null || routeId.isBlank()) {
            throw new IllegalArgumentException("routeId must not be blank");
        }

        return cache.get(routeId, () -> mbtaClient.fetchStops(routeId));
    }
}
