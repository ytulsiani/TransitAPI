package com.mbta.mbtaapi;

import com.google.common.cache.Cache;
import com.google.common.cache.CacheBuilder;
import java.io.IOException;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

public class LineService {
    private final MbtaClient mbtaClient;
    private final Cache<String, List<LineSummary>> cache;

    public LineService(MbtaClient mbtaClient) {
        this.mbtaClient = mbtaClient;
        this.cache =
                CacheBuilder.newBuilder()
                        .expireAfterWrite(5, TimeUnit.MINUTES)
                        .build();
    }

    public List<LineSummary> getLines() throws ExecutionException, IOException, InterruptedException {
        return cache.get(
                "lines",
                () -> {
                    List<LineSummary> fresh = mbtaClient.fetchLines();
                    return fresh;
                });
    }
}
